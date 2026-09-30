# SPDX-License-Identifier: GPL-3.0-only
#
# Added by kukudexuan1 (2026) as part of the modified mcp-cad distribution.
# Based on mcp-cad (https://github.com/Andiveli/mcp-cad), licensed under GNU GPL v3.0.
# See the LICENSE file in the mcp-cad directory for the full license text.

"""Quick test for get_model_json and get_entity_detail via MCP stdio protocol."""

import json
import subprocess
import time

SERVER = r"c:\Users\14170\Desktop\研究生课题\mcp-cad\src\McpCad.Server\bin\Debug\net8.0-windows\McpCad.Server.exe"

def send(proc, obj):
    proc.stdin.write((json.dumps(obj) + "\n").encode())
    proc.stdin.flush()

def recv(proc, timeout=8.0):
    start = time.time()
    while time.time() - start < timeout:
        line = proc.stdout.readline()
        if line:
            text = line.decode(errors="replace").strip()
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    print(f"  [non-json] {text[:120]}", flush=True)
        time.sleep(0.05)
    return None

def call_tool(proc, req_id, tool_name, args=None):
    send(proc, {"jsonrpc":"2.0","id":req_id,"method":"tools/call",
                "params":{"name":tool_name,"arguments":args or {}}})
    resp = recv(proc, timeout=20.0)
    if resp is None:
        print(f"  [TIMEOUT] {tool_name}", flush=True)
    return resp

def extract(resp):
    if resp is None:
        return None
    content = resp.get("result", {}).get("content", [{}])
    text = content[0].get("text", "") if content else ""
    try:
        return json.loads(text)
    except Exception:
        return text

def main():
    print("Starting MCP server...", flush=True)
    proc = subprocess.Popen([SERVER], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1.0)

    send(proc, {"jsonrpc":"2.0","id":1,"method":"initialize",
                "params":{"protocolVersion":"2024-11-05","capabilities":{},
                          "clientInfo":{"name":"test","version":"0.1"}}})
    init = recv(proc, timeout=6.0)
    if init:
        print(f"initialize OK: server={init.get('result',{}).get('serverInfo',{})}", flush=True)
    else:
        print("initialize FAILED"); proc.kill(); return

    send(proc, {"jsonrpc":"2.0","method":"notifications/initialized","params":{}})
    time.sleep(0.3)

    # --- inventor_connect ---
    print("\n--- inventor_connect ---", flush=True)
    d = extract(call_tool(proc, 2, "inventor_connect"))
    print(json.dumps(d, ensure_ascii=False, indent=2), flush=True)

    # --- get_model_json summary ---
    print("\n--- get_model_json summary ---", flush=True)
    d = extract(call_tool(proc, 3, "get_model_json",
                          {"include_faces": True, "include_edges": False, "max_faces": 32}))
    if d:
        summary = {k: v for k, v in d.items() if k != "bodies"}
        print("SUMMARY:", json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        for body in d.get("bodies", []):
            faces = body.pop("faces", []) or []
            print(f"\nBODY {body['entity_id']}: faces={body['face_count']} "
                  f"edges={body['edge_count']} vol={body.get('volume',0):.4f}", flush=True)
            for face in faces[:6]:
                adj = face.get("adjacency", {})
                print(f"  {face['entity_id']:10s} {face['surface_type']:10s} "
                      f"area={face.get('area',0):.4f}  "
                      f"nbrs={adj.get('neighboring_faces',[])[:3]}", flush=True)
            if len(faces) > 6:
                print(f"  ... ({len(faces)-6} more)", flush=True)

    # --- face:0 detail ---
    print("\n--- get_entity_detail('face:0') ---", flush=True)
    d = extract(call_tool(proc, 4, "get_entity_detail", {"entity_id": "face:0", "body_index": 0}))
    if d:
        d.pop("normal_samples", None)
        print(json.dumps(d, ensure_ascii=False, indent=2), flush=True)

    # --- edge:0 detail ---
    print("\n--- get_entity_detail('edge:0') ---", flush=True)
    d = extract(call_tool(proc, 5, "get_entity_detail", {"entity_id": "edge:0", "body_index": 0}))
    if d:
        print(json.dumps(d, ensure_ascii=False, indent=2), flush=True)

    # --- all faces: convexity + arc_span_deg, find end face ---
    print("\n--- all faces: convexity + arc_span_deg ---", flush=True)
    d7 = extract(call_tool(proc, 6, "get_model_json",
                           {"include_faces": True, "include_edges": False, "max_faces": 64}))
    end_face_id = None
    if d7:
        for body in d7.get("bodies", []):
            for face in (body.get("faces") or []):
                n   = face.get("normal_at_center") or []
                st  = face.get("surface_type", "?")
                arc = face.get("arc_span_deg")
                cv  = face.get("convexity", "?")
                nr  = [round(v, 2) for v in n]
                print(f"  {face['entity_id']:10s} {st:10s}  convexity={cv:8s}  "
                      f"arc_span={str(arc):6s}  n={nr}", flush=True)
                if n and abs(abs(n[0]) - 1.0) < 0.15 and end_face_id is None:
                    end_face_id = face["entity_id"]

    # --- end face cross_section ---
    if end_face_id:
        print(f"\n--- get_entity_detail('{end_face_id}') [end face / cross_section] ---", flush=True)
        d8 = extract(call_tool(proc, 7, "get_entity_detail",
                               {"entity_id": end_face_id, "body_index": 0}))
        if d8:
            d8.pop("normal_samples", None)
            cs = d8.pop("cross_section", None)
            print(json.dumps(d8, ensure_ascii=False, indent=2), flush=True)
            if cs:
                print(f"\ncross_section ({len(cs)} edges):", flush=True)
                for e in cs:
                    s = [round(v, 3) for v in (e.get("start") or [])]
                    en = [round(v, 3) for v in (e.get("end") or [])]
                    print(f"  {str(e.get('edge_id','?')):10s}  {e.get('curve_type','?'):8s}  "
                          f"start={s}  end={en}", flush=True)
            else:
                print("  cross_section: null", flush=True)

    proc.kill()
    print("\nDone.", flush=True)

if __name__ == "__main__":
    main()
