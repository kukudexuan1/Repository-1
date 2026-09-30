---
name: inventor-new-part
description: "Trigger: Crea en inventor, create in inventor, nueva parte inventor, new inventor part, abrir inventor. Connect to Inventor, create a new part, and start a sketch on the YZ plane ready for modeling."
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

## Activation Contract

Use this skill when the user says "Crea en inventor", "create in inventor", "nueva parte", or any variation that means "start a new part in Inventor". This is the entry point — the user wants a blank part with a sketch ready to go.

## Hard Rules

- ALWAYS use the **YZ plane** for the initial sketch. Never default to XY or XZ.
- NEVER skip `inventor_connect` — verify the connection before creating anything.
- ALWAYS create a **part** document, never an assembly.
- If `inventor_connect` fails, STOP and tell the user Inventor is not running.

## Execution Steps

1. Call `mcp-cad_inventor_connect` to connect to the running Autodesk Inventor instance.
2. If connection fails, stop and report: "No pude conectar a Inventor. ¿Está abierto?"
3. Call `mcp-cad_doc_new_part` to create a new part document.
4. Call `mcp-cad_sketch_create` with `plane="YZ"` to start a sketch on the YZ plane.
5. Report back with what's ready and ask what geometry to draw next.

## Output Contract

After successful execution, confirm:
- Connected to Inventor
- New part created
- Sketch active on YZ plane

Then ask the user what to draw: "Listo, parte nueva con sketch en plano YZ. ¿Qué querés dibujar?"

If any step fails, report which step failed and why. Do not continue to subsequent steps.
