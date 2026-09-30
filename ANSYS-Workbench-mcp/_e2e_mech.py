import os, time
os.environ["ANSYS_WORKBENCH_MCP_HOME"] = r"C:\Users\14170\Desktop\研究生课题\ANSYS-Workbench-mcp"
os.environ["ANSYS_RUNWB2"] = r"C:\Program Files\ANSYS Inc\v252\Framework\bin\Win64\RunWB2.exe"
import mcp_server as m

print("=== 1) create static structural system with STEP geometry ===")
t0 = time.time()
out = m.create_static_structural_system_live(
    project_dir=r"C:\Users\14170\Desktop\研究生课题\ANSYS-Workbench-mcp\runs\mech_e2e",
    geometry_file=r"D:\Inventor_Export\stepped_shaft.stp",
    timeout_seconds=300,
)
print("create elapsed %.1fs" % (time.time() - t0))
print(out[:300])

print("=== 2) run Mechanical script, read back body count ===")
mech = "\n".join([
    "model = ExtAPI.DataModel.Project.Model",
    "geom = model.Geometry",
    "bodies = geom.GetChildren(DataModelObjectCategory.Body, True)",
    "print('BODY_COUNT=' + str(bodies.Count))",
    "print('UNIT=' + str(ExtAPI.DataModel.Project.UnitSystem))",
])
t0 = time.time()
r = m.execute_mechanical_script(mech, timeout_seconds=400)
print("mech elapsed %.1fs" % (time.time() - t0))
print("RESULT:")
print(r[:800])
