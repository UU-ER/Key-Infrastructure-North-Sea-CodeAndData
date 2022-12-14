import numbers
from src.model_construction.generic_technology_constraints import *
import src.config_model as m_config


def add_technologies(nodename, b_node, model, data):
    r"""
    Adds all technologies as model blocks to respective node.

    This function initializes parameters and decision variables for all technologies at respective node.
    For each technology, it adds one block indexed by the set of all technologies at the node :math:`S_n`.
    This function adds Sets, Parameters, Variables and Constraints that are common for all technologies.
    For each technology type, individual parts are added. The following technology types are currently available:

    - Type 1: Renewable technology with cap_factor as input. Constructed with \
      :func:`src.model_construction.generic_technology_constraints.constraints_tec_type_1`
    - Type 2: n inputs -> n output, fuel and output substitution. Constructed with \
      :func:`src.model_construction.generic_technology_constraints.constraints_tec_type_2`
    - Type 3: n inputs -> n output, fuel and output substitution. Constructed with \
      :func:`src.model_construction.generic_technology_constraints.constraints_tec_type_3`
    - Type 6: Storage technology (1 input -> 1 output). Constructed with \
      :func:`src.model_construction.generic_technology_constraints.constraints_tec_type_6`

    **Set declarations:**

    - Set of input carriers
    - Set of output carriers

    **Parameter declarations:**

    - Min Size
    - Max Size
    - Output max (same as size max)
    - Unit CAPEX
    - Variable OPEX
    - Fixed OPEX

    **Variable declarations:**

    - Size (can be integer or continuous)
    - Input for each input carrier
    - Output for each output carrier
    - CAPEX
    - Variable OPEX
    - Fixed OPEX

    **Constraint declarations**
    - CAPEX, can be linear (for ``capex_model == 1``) or piecewise linear (for ``capex_model == 2``). Linear is defined as:

    .. math::
        CAPEX_{tec} = Size_{tec} * UnitCost_{tec}

    - Variable OPEX: defined per unit of output for the main carrier:

    .. math::
        OPEXvar_{t, tec} = Output_{t, maincarrier} * opex_{var} \forall t \in T

    - Fixed OPEX: defined as a fraction of annual CAPEX:

    .. math::
        OPEXfix_{tec} = CAPEX_{tec} * opex_{fix}

    :param str nodename: name of node for which technology is installed
    :param object b_node: pyomo block for respective node
    :param object model: pyomo model
    :param DataHandle data:  instance of a DataHandle
    :return: model
    """
    def init_technology_block(b_tec, tec):

        # region Get options from data
        tec_data = data.technology_data[nodename][tec]
        tec_type = tec_data['TechnologyPerf']['tec_type']
        capex_model = tec_data['Economics']['CAPEX_model']
        size_is_integer = tec_data['TechnologyPerf']['size_is_int']
        # endregion

        # region PARAMETERS

        # We need this shit because python does not accept single value in its build-in min function
        if isinstance(tec_data['TechnologyPerf']['size_min'], numbers.Number):
            size_min = tec_data['TechnologyPerf']['size_min']
        else:
            size_min = min(tec_data['TechnologyPerf']['size_min'])
        if isinstance(tec_data['TechnologyPerf']['size_max'], numbers.Number):
            size_max = tec_data['TechnologyPerf']['size_max']
        else:
            size_max = max(tec_data['TechnologyPerf']['size_max'])

        if size_is_integer:
            unit_size = u.dimensionless
        else:
            unit_size = u.MW
        b_tec.para_size_min = Param(domain=NonNegativeReals, initialize=size_min, units=unit_size)
        b_tec.para_size_max = Param(domain=NonNegativeReals, initialize=size_max, units=unit_size)
        b_tec.para_output_max = Param(domain=NonNegativeReals, initialize=size_max, units=u.MW)
        b_tec.para_unit_CAPEX = Param(domain=Reals, initialize=tec_data['Economics']['unit_CAPEX_annual'],
                                      units=u.EUR/unit_size)
        b_tec.para_OPEX_variable = Param(domain=Reals, initialize=tec_data['Economics']['OPEX_variable'],
                                         units=u.EUR/u.MWh)
        b_tec.para_OPEX_fixed = Param(domain=Reals, initialize=tec_data['Economics']['OPEX_fixed'],
                                      units=u.EUR/u.EUR)
        # endregion

        # region SETS
        b_tec.set_input_carriers = Set(initialize=tec_data['TechnologyPerf']['input_carrier'])
        b_tec.set_output_carriers = Set(initialize=tec_data['TechnologyPerf']['output_carrier'])
        # endregion

        # region DECISION VARIABLES
        # Input
        # TODO: calculate different bounds
        if not tec_type == 'RES':
            b_tec.var_input = Var(model.set_t, b_tec.set_input_carriers, within=NonNegativeReals,
                                  bounds=(b_tec.para_size_min, b_tec.para_size_max), units=u.MW)
        # Output
        b_tec.var_output = Var(model.set_t, b_tec.set_output_carriers, within=NonNegativeReals,
                               bounds=(0, b_tec.para_output_max), units=u.MW)
        # Size
        if size_is_integer:  # size
            b_tec.var_size = Var(within=NonNegativeIntegers, bounds=(b_tec.para_size_min, b_tec.para_size_max))
        else:
            b_tec.var_size = Var(within=NonNegativeReals, bounds=(b_tec.para_size_min, b_tec.para_size_max),
                                 units=u.MW)
        # Capex/Opex
        b_tec.var_CAPEX = Var(units=u.EUR)  # capex
        b_tec.var_OPEX_variable = Var(model.set_t, units=u.EUR)  # variable opex
        b_tec.var_OPEX_fixed = Var(units=u.EUR)  # fixed opex
        # endregion

        # region GENERAL CONSTRAINTS
        # Capex
        if capex_model == 1:
            b_tec.const_CAPEX = Constraint(expr=b_tec.var_size * b_tec.para_unit_CAPEX == b_tec.var_CAPEX)
        elif capex_model == 2:
            m_config.presolve.big_m_transformation_required = 1
            # TODO Implement link between bps and data
            b_tec.const_CAPEX = Piecewise(b_tec.var_CAPEX, b_tec.var_size,
                                          pw_pts=bp_x,
                                          pw_constr_type='EQ',
                                          f_rule=bp_y,
                                          pw_repn='SOS2')
        # fixed Opex
        b_tec.const_OPEX_fixed = Constraint(expr=b_tec.var_CAPEX * b_tec.para_OPEX_fixed == b_tec.var_OPEX_fixed)

        # variable Opex
        def init_OPEX_variable(const, t):
            return sum(b_tec.var_output[t, car] for car in b_tec.set_output_carriers) * b_tec.para_OPEX_variable == \
                   b_tec.var_OPEX_variable[t]
        b_tec.const_OPEX_variable = Constraint(model.set_t, rule=init_OPEX_variable)

        # Size constraint
        # if tec_type == 1: # we don't need size constraints for renewable technologies
        #     pass
        # elif tec_type == 6: # This is defined in the generic technology constraints
        #     pass
        # else: # in terms of input
        #     def init_output_constraint(const, t):
        #         return sum(b_tec.var_input[t, car_input] for car_input in b_tec.set_input_carriers) \
        #                <= b_tec.var_size
        #     b_tec.const_size = Constraint(model.set_t, rule=init_output_constraint)

        # endregion

        # region TECHNOLOGY TYPES
        if tec_type == 'RES': # Renewable technology with cap_factor as input
            b_tec = constraints_tec_RES(model, b_tec, tec_data)

        elif tec_type == 'CONV1': # n inputs -> n output, fuel and output substitution
            b_tec = constraints_tec_CONV1(model, b_tec, tec_data)

        elif tec_type == 'CONV2': # n inputs -> n output, fuel and output substitution
            b_tec = constraints_tec_CONV2(model, b_tec, tec_data)

        elif tec_type == 'CONV3':  # 1 input -> n outputs, output flexible, linear performance
            b_tec = constraints_tec_CONV3(model, b_tec, tec_data)

        elif tec_type == 'STOR': # Storage technology (1 input -> 1 output)
            b_tec = constraints_tec_STOR(model, b_tec, tec_data)

    b_node.tech_blocks = Block(b_node.set_tecsAtNode, rule=init_technology_block)
    return b_node
