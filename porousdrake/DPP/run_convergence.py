from firedrake import *
from porousdrake.DPP.convergence.solvers import dgls, sdhm
from firedrake.petsc import PETSc

from porousdrake.DPP.convergence import processor
import porousdrake.setup.solvers_parameters as parameters
from porousdrake.post_processing.writers import write_pvd_mixed_formulations

import sys

try:
    import matplotlib.pyplot as plt

    plt.rcParams["contour.corner_mask"] = False
    plt.close("all")
except:
    warning("Matplotlib not imported")

single_run = False
nx, ny = 10, 10
Lx, Ly = 1.0, 1.0
quadrilateral = True
degree = 1
last_degree = 4
mesh = RectangleMesh(nx, ny, Lx, Ly, quadrilateral=quadrilateral)

# Mesh options
mesh_quad = [False, True]  # Triangles, Quads
mesh_parameters = [True, False]

# Solver options
solvers_options = {
    #    'cgls_full': cgls,
    #    'cgls_div': cgls,
    #    'mgls': cgls,
    #    'mgls_full': cgls,
    #    'mvh_full': cgls,
    #    'mvh_div': cgls,
    #    'mvh': cgls,
    #    'dgls_full': dgls,
    #    'dgls_div': dgls,
    #    'dmgls': dgls,
    "dmgls_full": dgls,
    "dmvh_full": dgls,
    "dmvh_div": dgls,
    "dmvh": dgls,
    "sdhm_full": sdhm,
    "sdhm_div": sdhm,
    "hmgls": sdhm,
    "hmgls_full": sdhm,
    "hmvh_full": sdhm,
    "hmvh_div": sdhm,
    "hmvh": sdhm,
}

# Choosing the solver
solver = dgls

# Convergence range
n = [5, 10, 15, 20, 25, 30]
# n = [4, 8, 16, 32, 64, 128]

# Cold run
if single_run:
    p1_sol, v1_sol, p2_sol, v2_sol, p_e_1, v_e_1, p_e_2, v_e_2 = solver(
        mesh=mesh,
        degree=degree,
        delta_0=parameters.delta_0,
        delta_1=parameters.delta_1,
        delta_2=parameters.delta_2,
        delta_3=parameters.delta_3,
        # beta_0=parameters.beta_0,
        eta_u=parameters.eta_u,
        eta_p=parameters.eta_p,
        mesh_parameter=parameters.mesh_parameter,
    )

    plot(p1_sol)
    plot(p_e_1)
    plot(p2_sol)
    plot(p_e_2)
    plot(v1_sol)
    plot(v_e_1)
    plot(v2_sol)
    plot(v_e_2)
    plt.show()
    print("*** Single run OK ***\n")
    # write_pvd_mixed_formulations('teste_import', mesh, degree, p1_sol, v1_sol, p2_sol, v2_sol)
    sys.exit()

# Sanity check for keys among solvers_options and solvers_args
assert set(solvers_options.keys()).issubset(parameters.solvers_args.keys())

for element in mesh_quad:
    for current_solver in solvers_options:
        for mesh_parameter in mesh_parameters:
            if element:
                element_kind = "quad"
            else:
                element_kind = "tri"
            if mesh_parameter:
                mesh_par = ""
            else:
                mesh_par = "meshless_par"

            # Setting the output file name
            name = "%s_%s_%s_errors" % (current_solver, mesh_par, element_kind)
            PETSc.Sys.Print("*******************************************\n")
            PETSc.Sys.Print("*** Begin case: %s ***\n" % name)

            # Selecting the solver and its kwargs
            solver = solvers_options[current_solver]
            kwargs = parameters.solvers_args[current_solver]

            # Appending the mesh parameter option to kwargs
            kwargs["mesh_parameter"] = mesh_parameter

            # Performing the convergence study
            processor.convergence_hp(
                solver,
                min_degree=degree,
                max_degree=degree + last_degree,
                numel_xy=n,
                quadrilateral=quadrilateral,
                name=name,
                **kwargs
            )
            PETSc.Sys.Print("\n*** End case: %s ***" % name)
            PETSc.Sys.Print("*******************************************\n")
