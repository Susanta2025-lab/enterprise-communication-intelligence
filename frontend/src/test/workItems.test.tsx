import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { axe } from "jest-axe";
import { App } from "../App";
import { EciApiClient } from "../api/client";
import type { Candidate, WorkDetail } from "../api/workItems";
import { WorkForm } from "../components/workItems/WorkForm";
import { CandidatePanel } from "../components/workItems/CandidatePanel";
import { AuthStub, TEST_CONFIG, createAuthSession } from "./fixtures";
const id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const session = createAuthSession({ isAuthenticated: true, accountKey: "alice", permissions: ["communications:analyze"] });
const item: WorkDetail = { id, title: "Reviewed action", description: null, kind: "action", status: "open", version: 1, due: { kind: "none" }, business_context_id: null, creation_origin: "manual", created_at: "2026-09-27T12:00:00Z", updated_at: "2026-09-27T12:00:00Z", archived_at: null, completed_at: null, cancelled_at: null, confirmed_at: null, overdue: false, sources: [] };
function json(value: unknown, status = 200, headers = {}) { return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json", ...headers } }); }
function setup(handler: (url: URL, init?: RequestInit) => Response | Promise<Response>, path = "/tracking") {
  const fetcher = vi.fn<typeof fetch>(async (input, init) => { const url = new URL(String(input)); if (url.pathname === "/api/v1/me") return json({ application_role: "user", is_owner: false }); if (url.pathname === "/api/v1/contexts") return json({ items: [], limit: 50, offset: 0 }); return handler(url, init); });
  const api = new EciApiClient({ baseUrl: "http://localhost:8000", tokenProvider: { acquireAccessToken: async () => "test" }, fetchImpl: fetcher });
  window.history.replaceState(null, "", path);
  const view = render(<AuthStub session={session}><App apiClient={api} config={TEST_CONFIG} /></AuthStub>);
  return { ...view, api, fetcher };
}
function isolated(_api: EciApiClient, child: React.ReactNode) {
  return render(<AuthStub session={session}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{child}</MemoryRouter></QueryClientProvider></AuthStub>);
}
async function fill() { const user = userEvent.setup(); await user.selectOptions(screen.getByLabelText("Kind"), "action"); await user.type(screen.getByLabelText("Reviewed title"), "Reviewed action"); await user.selectOptions(screen.getByLabelText("Due mode"), "none"); return user; }
describe("Tracking browser flows", () => {
  it("lists owned items and sends filters/sort/pagination to server", async () => {
    const { fetcher } = setup(() => json({ items: Array.from({ length: 20 }, (_, n) => ({ ...item, id: `${id}${n}` })), limit: 20, offset: 0 }));
    await screen.findAllByText("Reviewed action"); const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(fetcher.mock.calls.some(([u]) => String(u).includes("offset=20"))).toBe(true));
    await user.selectOptions(screen.getByLabelText("Due kind"), "date"); await user.selectOptions(screen.getByLabelText("Sort"), "due_asc");
    await waitFor(() => expect(fetcher.mock.calls.some(([u]) => String(u).includes("due_kind=date") && String(u).includes("sort=due_asc") && String(u).includes("offset=0"))).toBe(true));
  });
  it.each([200,201])("creates without mailbox and accepts HTTP %s", async status => {
    const calls: unknown[] = [];
    setup((url, init) => { if (init?.method === "POST") { calls.push(JSON.parse(String(init.body))); return json(item,status); } if (url.pathname.endsWith("/events")) return json({ items: [], limit:20, offset:0 }); if (url.pathname.endsWith(id)) return json(item); return json({ items: [], limit:20, offset:0 }); });
    await userEvent.click(await screen.findByRole("button", { name: "Create Work Item" })); const user = await fill();
    await user.click(screen.getByRole("button", { name: "Create Work Item" }).closest("form")!.querySelector("button[type=submit]")!);
    await waitFor(() => expect(calls).toHaveLength(1)); expect(calls[0]).toMatchObject({ kind: "action", due:{kind:"none"}, business_context_id:null });
  });
  it("retains key and exact payload after ambiguous failure", async () => {
    const bodies: string[] = []; const api = new EciApiClient({ baseUrl:"http://localhost", tokenProvider:{acquireAccessToken:async()=>"t"}, fetchImpl:vi.fn(async (_u,init) => { if (init?.method === "POST") { bodies.push(String(init.body)); if (bodies.length === 1) throw new TypeError("offline"); return json(item); } return json({items:[]}); }) });
    const done = vi.fn(); isolated(api,<WorkForm api={api} onDone={done} onCancel={vi.fn()} />); const user=await fill(); await user.click(screen.getByRole("button",{name:"Create Work Item"})); await screen.findByRole("alert"); expect(screen.getByLabelText("Reviewed title")).toBeDisabled(); await user.click(screen.getByRole("button",{name:"Retry original creation"})); await waitFor(()=>expect(done).toHaveBeenCalledWith(id)); expect(bodies[1]).toBe(bodies[0]);
  });
  it("gates navigation and reads by capability", async () => {
    const { rerender, api, fetcher } = setup(()=>json({items:[]})); await screen.findByText("No work items match these filters."); fetcher.mockClear(); rerender(<AuthStub session={{...session,accountKey:"bob",permissions:[]}}><App apiClient={api} config={TEST_CONFIG}/></AuthStub>); expect(screen.getByRole("alert")).toHaveTextContent("requires"); expect(screen.queryByRole("link",{name:"Tracking"})).not.toBeInTheDocument(); expect(fetcher.mock.calls.some(([u])=>String(u).includes("work-items"))).toBe(false);
  });
  it("isolates identity changes and cancels pending reads", async () => {
    let resolve!: (r:Response)=>void; let signal: AbortSignal | null | undefined;
    const { rerender, api }=setup((_url,init)=>{ signal=init?.signal; return new Promise(r=>{resolve=r;}); });
    await waitFor(()=>expect(signal).toBeDefined()); const oldSignal=signal; const finish=resolve;
    rerender(<AuthStub session={{...session,accountKey:"bob"}}><App apiClient={api} config={TEST_CONFIG}/></AuthStub>);
    await waitFor(()=>expect(oldSignal?.aborted).toBe(true)); finish(json({items:[item],limit:20,offset:0})); expect(screen.queryByText(item.title)).not.toBeInTheDocument();
  });
  it.each(["completed","cancelled"] as const)("requires reopen for %s and submits version", async status=>{
    const writes: unknown[]=[]; setup((url,init)=>{if(init?.method==="POST"){writes.push(JSON.parse(String(init.body)));return json({...item,status:"open",version:2});}return json(url.pathname.endsWith("/events")?{items:[]}: {...item,status});},`/tracking/${id}`);
    await screen.findByRole("button",{name:"Reopen"}); expect(screen.queryByRole("button",{name:"Edit work item"})).not.toBeInTheDocument(); await userEvent.click(screen.getByRole("button",{name:"Reopen"})); expect(screen.getByRole("dialog")).toBeInTheDocument(); await userEvent.click(screen.getByRole("button",{name:"Confirm change"})); await waitFor(()=>expect(writes[0]).toEqual({expected_version:1,status:"open",reopen:true}));
  });
  it("archived items only offer restore and preserve unavailable sources",async()=>{
    setup(url=>json(url.pathname.endsWith("/events")?{items:[]}:{...item,archived_at:item.created_at,sources:[{source_kind:"attachment_analysis",availability:"unavailable"}]}),`/tracking/${id}`);
    await screen.findByRole("button",{name:"Restore"}); expect(screen.queryByRole("button",{name:"Edit work item"})).not.toBeInTheDocument(); expect(screen.getByText(/attachment_analysis: unavailable/)).toBeInTheDocument();
  });
  it("has labeled accessible manual controls and initial focus",async()=>{
    const api=new EciApiClient({baseUrl:"http://localhost",tokenProvider:{acquireAccessToken:async()=>"t"},fetchImpl:vi.fn(async()=>json({items:[]}))});const {container}=isolated(api,<WorkForm api={api} onDone={vi.fn()} onCancel={vi.fn()}/>);expect(screen.getByLabelText("Reviewed title")).toHaveFocus(); expect((await axe(container)).violations).toEqual([]);
  });
});
describe("persisted advisory conversion",()=>{
  it.each(["action_items","potential_action_mentions","potential_dates"] as const)("reviews %s without automatic creation or pairing",async field=>{
    const value="Observe "+"x".repeat(260); const candidate:Candidate={candidate:{projection_version:1,source_kind:field==="action_items"?"communication_analysis":"attachment_analysis",source_id:id,field,index:0,digest:"a".repeat(64)},value,advisory:true,truncated:true,warnings:["Review uncertainty"],limitations:["Bounded extraction"]};
    const posts: unknown[]=[];const api=new EciApiClient({baseUrl:"http://localhost",tokenProvider:{acquireAccessToken:async()=>"t"},fetchImpl:vi.fn(async(u,init)=>{if(init?.method==="POST"){posts.push(JSON.parse(String(init.body)));return json(item,201);}return json({items:String(u).includes("candidates")?[candidate]:[]});})});isolated(api,<CandidatePanel api={api} source={{source_kind:candidate.candidate.source_kind,source_id:id}}/>);
    const user=userEvent.setup();await user.click(screen.getByRole("button",{name:"Review tracking candidates"}));await screen.findByText(value);expect(posts).toHaveLength(0);await user.click(screen.getByRole("button",{name:"Create tracked item"}));expect(screen.getByLabelText("Reviewed title")).toHaveValue("");expect(screen.getByLabelText("Due mode")).toHaveValue("");expect(screen.getByText("Review uncertainty")).toBeInTheDocument();await user.click(screen.getByRole("button",{name:"Cancel"}));expect(posts).toHaveLength(0);await user.click(screen.getByRole("button",{name:"Create tracked item"}));await fill();await user.click(screen.getByRole("button",{name:"Confirm and create tracked item"}));await waitFor(()=>expect(posts).toHaveLength(1));expect(posts[0]).toMatchObject({title:"Reviewed action",candidate:candidate.candidate,confirmed:true,due:{kind:"none"}});
  });
});

describe("tracking conflict and due recovery", () => {
  it("submits date-only verbatim only after timezone confirmation", async () => {
    const posts: unknown[]=[];
    const api=new EciApiClient({baseUrl:"http://localhost",tokenProvider:{acquireAccessToken:async()=>"t"},fetchImpl:vi.fn(async(_u,init)=>{if(init?.method==="POST"){posts.push(JSON.parse(String(init.body)));return json(item,201);}return json({items:[]});})});
    isolated(api,<WorkForm api={api} onDone={vi.fn()} onCancel={vi.fn()}/>);
    const user=await fill(); await user.selectOptions(screen.getByLabelText("Due mode"),"date"); await user.type(screen.getByLabelText("Calendar date"),"2026-09-27");
    await user.clear(screen.getByLabelText("IANA timezone"));await user.type(screen.getByLabelText("IANA timezone"),"Pacific/Kiritimati");
    await user.click(screen.getByRole("button",{name:"Create Work Item"}));expect(await screen.findByRole("alert")).toHaveTextContent("Confirm the business timezone"); expect(posts).toHaveLength(0);
    await user.click(screen.getByRole("checkbox"));await user.click(screen.getByRole("button",{name:"Create Work Item"}));await waitFor(()=>expect(posts[0]).toMatchObject({due:{kind:"date",date:"2026-09-27",timezone:"Pacific/Kiritimati"}}));
  });
  it("requires deliberate DST offset choice before creating",async()=>{
    const posts: unknown[]=[];const api=new EciApiClient({baseUrl:"http://localhost",tokenProvider:{acquireAccessToken:async()=>"t"},fetchImpl:vi.fn(async(_u,init)=>{if(init?.method==="POST"){posts.push(JSON.parse(String(init.body)));return json(item);}return json({items:[]});})});
    isolated(api,<WorkForm api={api} onDone={vi.fn()} onCancel={vi.fn()}/>);const user=await fill();await user.selectOptions(screen.getByLabelText("Due mode"),"datetime");
    // Native datetime-local input is set using its browser value format.
    const { fireEvent } = await import("@testing-library/react");fireEvent.change(screen.getByLabelText("Local date and time"),{target:{value:"2026-11-01T01:30"}});
    await user.clear(screen.getByLabelText("IANA timezone"));await user.type(screen.getByLabelText("IANA timezone"),"America/New_York");await user.click(screen.getByRole("checkbox"));await user.click(screen.getByRole("button",{name:"Create Work Item"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("repeats");expect(posts).toHaveLength(0);await user.selectOptions(screen.getByLabelText("Repeated-time offset"),"2026-11-01T01:30:00-05:00");await user.click(screen.getByRole("button",{name:"Create Work Item"}));await waitFor(()=>expect(posts[0]).toMatchObject({due:{kind:"datetime",at:"2026-11-01T01:30:00-05:00",timezone:"America/New_York"}}));
  });
  it("keeps creation conflicts visible and retains the original request",async()=>{
    const api=new EciApiClient({baseUrl:"http://localhost",tokenProvider:{acquireAccessToken:async()=>"t"},fetchImpl:vi.fn(async(_u,init)=>init?.method==="POST"?json({code:"work_item_creation_key_conflict"},409):json({items:[]}))});isolated(api,<WorkForm api={api} onDone={vi.fn()} onCancel={vi.fn()}/>);const user=await fill();await user.click(screen.getByRole("button",{name:"Create Work Item"}));expect(await screen.findByRole("alert")).toHaveTextContent("different fields");expect(screen.getByLabelText("Reviewed title")).toBeDisabled();
  });
  it("shows stale edit conflicts and requires explicit reload/review",async()=>{
    const writes: unknown[]=[];setup((url,init)=>{if(init?.method==="PATCH"){writes.push(JSON.parse(String(init.body)));return json({code:"work_item_version_conflict"},409);}return json(url.pathname.endsWith("/events")?{items:[]}:item);},`/tracking/${id}`);
    await userEvent.click(await screen.findByRole("button",{name:"Edit work item"}));await userEvent.click(screen.getByRole("button",{name:"Save reviewed changes"}));expect(await screen.findByRole("alert")).toHaveTextContent("conflicts");expect(writes).toHaveLength(1);expect(writes[0]).toMatchObject({expected_version:1});await userEvent.click(screen.getByRole("button",{name:"Reload and review"}));await waitFor(()=>expect(screen.queryByLabelText("Reviewed title")).not.toBeInTheDocument());
  });
  it.each(["work_item_candidate_changed","work_item_candidate_already_tracked"])("handles %s safely",async code=>{
    const { WorkError }=await import("../components/workItems/WorkError");const { EciApiError }=await import("../api/errors");const api=new EciApiClient({baseUrl:"http://localhost",tokenProvider:{acquireAccessToken:async()=>"t"}});isolated(api,<WorkError error={new EciApiError(409,"conflict","safe",null,code,`/api/v1/work-items/${id}`)}/>);expect(screen.getByRole("alert")).toHaveTextContent(code.includes("changed")?"observation changed":"already tracked");expect(screen.getByRole("link")).toHaveAttribute("href",`/tracking/${id}`);
  });
  it.each([401,403,404,422,503])("shows safe tracking HTTP %s errors",async status=>{
    const { WorkError }=await import("../components/workItems/WorkError");const { EciApiError, kindForStatus }=await import("../api/errors");const api=new EciApiClient({baseUrl:"http://localhost",tokenProvider:{acquireAccessToken:async()=>"t"}});isolated(api,<WorkError error={new EciApiError(status,kindForStatus(status),"secret raw response")}/>);expect(screen.getByRole("alert")).not.toHaveTextContent("secret raw response");
  });
  it("context Tracking uses direct server context filtering even when archived",async()=>{
    const calls:string[]=[];setup(url=>{calls.push(url.toString());if(url.pathname===`/api/v1/contexts/${id}`)return json({id,title:"Archived context",type:"project",status:"archived",created_at:item.created_at,updated_at:item.updated_at});if(url.pathname==="/api/v1/work-items")return json({items:[{...item,business_context_id:id}],limit:20,offset:0});return json({items:[]});},`/contexts/${id}`);
    await userEvent.click(await screen.findByRole("tab",{name:"Tracking"}));await screen.findByText(item.title);expect(calls.some(u=>u.includes(`business_context_id=${id}`))).toBe(true);expect(calls.some(u=>u.includes("/communications"))).toBe(false);
  });
});

describe("creation recovery and mutation isolation", () => {
  it("closing and reopening an uncertain manual creation retains its key",async()=>{
    const bodies:string[]=[];setup((url,init)=>{if(init?.method==="POST"){bodies.push(String(init.body));throw new TypeError("lost response");}if(url.pathname.endsWith("/events"))return json({items:[]});return json({items:[],limit:20,offset:0});});
    await userEvent.click(await screen.findByRole("button",{name:"Create Work Item"}));const user=await fill();await user.click(screen.getByRole("button",{name:"Create Work Item"}));await screen.findByRole("alert");await user.click(screen.getByRole("button",{name:"Cancel"}));await user.click(screen.getByRole("button",{name:"Create Work Item"}));expect(screen.getByLabelText("Reviewed title")).toHaveValue("Reviewed action");await user.click(screen.getByRole("button",{name:"Retry original creation"}));await waitFor(()=>expect(bodies).toHaveLength(2));expect(bodies[1]).toBe(bodies[0]);
  });
  it("identity change aborts pending creation and discards its late success",async()=>{
    let resolve!: (r:Response)=>void; let signal: AbortSignal | null | undefined;
    const {rerender,api}=setup((_url,init)=>{if(init?.method==="POST"){signal=init.signal;return new Promise(r=>{resolve=r;});}return json({items:[],limit:20,offset:0});});
    await userEvent.click(await screen.findByRole("button",{name:"Create Work Item"}));const user=await fill();await user.click(screen.getByRole("button",{name:"Create Work Item"}));await waitFor(()=>expect(signal).toBeDefined());
    rerender(<AuthStub session={{...session,accountKey:"bob"}}><App apiClient={api} config={TEST_CONFIG}/></AuthStub>);await waitFor(()=>expect(signal?.aborted).toBe(true));resolve(json(item,201));await user.click(await screen.findByRole("button",{name:"Create Work Item"}));expect(screen.getByLabelText("Reviewed title")).toHaveValue("");expect(window.location.pathname).toBe("/tracking");
  });
  it("invalidates both context histories and current-association lists",async()=>{
    const { renderHook, act }=await import("@testing-library/react");const { useInvalidateTracking }=await import("../hooks/useWorkItems");const client=new QueryClient();
    const keys=[["contexts","old","timeline"],["contexts","new","timeline"],["work-items","alice","list",{business_context_id:"old"}],["work-items","alice","list",{business_context_id:"new"}]];
    keys.forEach(key=>client.setQueryData(key,{items:[]}));const {result}=renderHook(()=>useInvalidateTracking(),{wrapper:({children})=><QueryClientProvider client={client}>{children}</QueryClientProvider>});await act(()=>result.current());keys.forEach(key=>expect(client.getQueryState(key)?.isInvalidated).toBe(true));
  });
  it.each(["In progress","Complete","Cancel item","Archive"])("confirms %s with expected_version",async label=>{
    const writes:unknown[]=[];setup((url,init)=>{if(init?.method==="POST"){writes.push(JSON.parse(String(init.body)));return json(item);}return json(url.pathname.endsWith("/events")?{items:[]}:item);},`/tracking/${id}`);await userEvent.click(await screen.findByRole("button",{name:label}));expect(writes).toHaveLength(0);expect(screen.getByRole("button",{name:"Cancel"})).toHaveFocus();await userEvent.click(screen.getByRole("button",{name:"Confirm change"}));await waitFor(()=>expect(writes).toHaveLength(1));expect(writes[0]).toMatchObject({expected_version:1});
  });
});

describe("context edits and attachment provenance",()=>{
  it.each([null,"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"])("explicitly changes context to %s",async target=>{
    const bodies:unknown[]=[];const api=new EciApiClient({baseUrl:"http://localhost",tokenProvider:{acquireAccessToken:async()=>"t"},fetchImpl:vi.fn(async(_u,init)=>{if(init?.method==="PATCH"){bodies.push(JSON.parse(String(init.body)));return json(item);}return json({items:[{id:"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",title:"Destination",status:"active"}]});})});
    isolated(api,<WorkForm api={api} item={{...item,business_context_id:id}} onDone={vi.fn()} onCancel={vi.fn()}/>);await screen.findByText("Destination");await userEvent.selectOptions(screen.getByLabelText("Business Context (optional)"),target??"");await userEvent.click(screen.getByRole("button",{name:"Save reviewed changes"}));await waitFor(()=>expect(bodies[0]).toMatchObject({business_context_id:target,expected_version:1}));
  });
  it("uses ordinary attachment action locator unchanged and never analyzes or sends",async()=>{
    const candidate:Candidate={candidate:{projection_version:1,source_kind:"attachment_analysis",source_id:id,field:"action_items",index:3,digest:"b".repeat(64)},value:{description:"Review invoice",due_date:"advisory only"},advisory:true,truncated:false,warnings:[],limitations:[]};
    const calls:{path:string;method:string;body?:unknown}[]=[];const api=new EciApiClient({baseUrl:"http://localhost",tokenProvider:{acquireAccessToken:async()=>"t"},fetchImpl:vi.fn(async(u,init)=>{const path=new URL(String(u)).pathname;calls.push({path,method:init?.method??"GET",body:init?.body?JSON.parse(String(init.body)):undefined});if(path==="/api/v1/work-items/from-analysis")return json(item,201);if(path==="/api/v1/work-items/candidates")return json({items:[candidate]});if(path==="/api/v1/contexts")return json({items:[]});throw new Error("Forbidden side effect");})});
    isolated(api,<CandidatePanel api={api} source={{source_kind:"attachment_analysis",source_id:id}}/>);await userEvent.click(screen.getByRole("button",{name:"Review tracking candidates"}));await userEvent.click(await screen.findByRole("button",{name:"Create tracked item"}));const user=await fill();await user.click(screen.getByRole("button",{name:"Confirm and create tracked item"}));await waitFor(()=>expect(calls.filter(c=>c.method==="POST")).toHaveLength(1));expect(calls.find(c=>c.method==="POST")?.body).toMatchObject({candidate:candidate.candidate,due:{kind:"none"},confirmed:true});
  });
  it("resets selected review when the mailbox analysis source changes",async()=>{
    const api=new EciApiClient({baseUrl:"http://localhost",tokenProvider:{acquireAccessToken:async()=>"t"},fetchImpl:vi.fn(async()=>json({items:[{candidate:{projection_version:1,source_kind:"communication_analysis",source_id:id,field:"action_items",index:0,digest:"a".repeat(64)},value:"Old observation",warnings:[],limitations:[],truncated:false,advisory:true}]}))});
    const client=new QueryClient();const tree=(sourceId:string)=><AuthStub session={session}><QueryClientProvider client={client}><MemoryRouter><CandidatePanel api={api} source={{source_kind:"communication_analysis",source_id:sourceId}}/></MemoryRouter></QueryClientProvider></AuthStub>;
    const view=render(tree(id));await userEvent.click(screen.getByRole("button",{name:"Review tracking candidates"}));await userEvent.click(await screen.findByRole("button",{name:"Create tracked item"}));await userEvent.type(screen.getByLabelText("Reviewed title"),"Old mailbox draft");view.rerender(tree("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"));expect(screen.queryByLabelText("Reviewed title")).not.toBeInTheDocument();expect(screen.queryByText("Old observation")).not.toBeInTheDocument();
  });
});

describe("ContextPicker completion checks", () => {
  it("pages owned contexts on the server and preserves a selection outside the page",async()=>{
    const { ContextPicker }=await import("../components/workItems/ContextPicker");
    const requests:URL[]=[];const api=new EciApiClient({baseUrl:"http://localhost",tokenProvider:{acquireAccessToken:async()=>"t"},fetchImpl:vi.fn(async u=>{const url=new URL(String(u));requests.push(url);return json({items:url.searchParams.get("offset")==="0"?Array.from({length:20},(_,i)=>({id:String(i),title:`Context ${i}`,status:"active"})):[],limit:20,offset:0});})});
    isolated(api,<ContextPicker api={api} value="previous" onChange={vi.fn()} includeArchived/>);
    await screen.findByText("Context 19");expect(screen.getByLabelText("Business Context (optional)")).toHaveValue("previous");await userEvent.click(screen.getByRole("button",{name:"Next contexts"}));await waitFor(()=>expect(requests.some(u=>u.searchParams.get("offset")==="20"&&u.searchParams.get("include_archived")==="true")).toBe(true));await waitFor(()=>expect(screen.getByRole("button",{name:"Next contexts"})).toBeDisabled());expect(screen.getByLabelText("Business Context (optional)")).toHaveValue("previous");
  });
  it("allows correcting an archived-context creation rejection without duplicating keys",async()=>{
    const bodies:Record<string,unknown>[]=[];const api=new EciApiClient({baseUrl:"http://localhost",tokenProvider:{acquireAccessToken:async()=>"t"},fetchImpl:vi.fn(async(_u,init)=>{if(init?.method==="POST"){bodies.push(JSON.parse(String(init.body)));return bodies.length===1?json({code:"work_item_context_archived"},409):json(item,201);}return json({items:[]});})});
    isolated(api,<WorkForm api={api} contextId={id} onDone={vi.fn()} onCancel={vi.fn()}/>);const user=await fill();await user.click(screen.getByRole("button",{name:"Create Work Item"}));expect(await screen.findByRole("alert")).toHaveTextContent("context is archived");await user.selectOptions(screen.getByLabelText("Business Context (optional)"),"");await user.click(screen.getByRole("button",{name:"Create Work Item"}));await waitFor(()=>expect(bodies).toHaveLength(2));expect(bodies[0].creation_key).toBe(bodies[1].creation_key);expect(bodies[1].business_context_id).toBeNull();
  });
});

it("recovers a closed uncertain confirmation even when its persisted source disappears",async()=>{
  const { CreationDraftContext }=await import("../components/workItems/creationDrafts");
  const candidate:Candidate={candidate:{projection_version:1,source_kind:"attachment_analysis",source_id:id,field:"potential_dates",index:0,digest:"a".repeat(64)},value:"Original date observation",advisory:true,truncated:false,warnings:[],limitations:[]};
  const bodies:string[]=[];let missing=false;
  const api=new EciApiClient({baseUrl:"http://localhost",tokenProvider:{acquireAccessToken:async()=>"t"},fetchImpl:vi.fn(async(u,init)=>{if(init?.method==="POST"){bodies.push(String(init.body));if(bodies.length===1){missing=true;throw new TypeError("response lost");}return json(item,200);}if(String(u).includes("candidates"))return missing?json({},404):json({items:[candidate]});return json({items:[]});})});
  isolated(api,<CreationDraftContext.Provider value={new Map()}><CandidatePanel api={api} source={{source_kind:"attachment_analysis",source_id:id}}/></CreationDraftContext.Provider>);
  const user=userEvent.setup();await user.click(screen.getByRole("button",{name:"Review tracking candidates"}));await user.click(await screen.findByRole("button",{name:"Create tracked item"}));await fill();await user.click(screen.getByRole("button",{name:"Confirm and create tracked item"}));await screen.findByRole("alert");await user.click(screen.getByRole("button",{name:"Close tracking candidates"}));await user.click(screen.getByRole("button",{name:"Review tracking candidates"}));expect(screen.getByText("Original date observation")).toBeInTheDocument();await user.click(screen.getByRole("button",{name:"Retry original creation"}));await waitFor(()=>expect(bodies).toHaveLength(2));expect(bodies[1]).toBe(bodies[0]);
});


it("keeps an unsupported server timezone readable and requires explicit deadline review", async () => {
  const due = {kind: "datetime" as const, at: "2026-09-27T12:00:00+00:00", timezone: "Unavailable/BrowserZone"};
  const writes: unknown[] = [];
  setup((url, init) => {
    if (init?.method === "PATCH") writes.push(init.body);
    return json(url.pathname.endsWith("/events") ? {items: []} : {...item, due});
  }, `/tracking/${id}`);
  expect(await screen.findByText(/timezone unavailable in this browser/)).toHaveTextContent(due.at);
  await userEvent.click(screen.getByRole("button", {name: "Edit work item"}));
  expect(screen.getByRole("alert")).toHaveTextContent("server value remains authoritative");
  expect(screen.getByLabelText("Local date and time")).toHaveValue("");
  expect(screen.getByRole("checkbox")).not.toBeChecked();
  expect(writes).toHaveLength(0);
});

it("a full application remount clears uncertain drafts without automatically resubmitting", async () => {
  const bodies: string[] = [];
  const handler = (_url: URL, init?: RequestInit) => {
    if (init?.method === "POST") { bodies.push(String(init.body)); throw new TypeError("lost response"); }
    return json({items: [], limit: 20, offset: 0});
  };
  const first = setup(handler);
  await userEvent.click(await screen.findByRole("button", {name: "Create Work Item"}));
  const user = await fill();
  await user.click(screen.getByRole("button", {name: "Create Work Item"}));
  await screen.findByRole("alert");
  expect(screen.getByRole("status")).toHaveTextContent("inspect Tracking");
  first.unmount();
  setup(handler);
  await user.click(await screen.findByRole("button", {name: "Create Work Item"}));
  expect(screen.getByLabelText("Reviewed title")).toHaveValue("");
  expect(bodies).toHaveLength(1);
});
