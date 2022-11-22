from pyomo.environ import *
from pyomo.environ import units as u
from src.model_construction.construct_nodes import add_nodes
from src.model_construction.construct_networks import add_networks
from src.model_construction.construct_energybalance import add_energybalance

import numpy as np
import dill as pickle
import pandas as pd

class energyhub:
    r"""
    Class to construct and manipulate an energy system model.

    When constructing an instance, it reads data to the instance and defines relevant model sets:

    **Set declarations:**

    - Set of nodes :math:`N`
    - Set of carriers :math:`M`
    - Set of time steps :math:`T`
    - Set of weather variables :math:`W`
    - Set of technologies at each node :math:`S_n, n \in N`

    """
    def __init__(self, data):
        """
        Constructor of the energyhub class.
        """
        # INITIALIZE MODEL
        self.model = ConcreteModel()

        # DEFINE SETS
        sets = data.topology
        self.model.set_nodes = Set(initialize=sets['nodes'])  # Nodes
        self.model.set_carriers = Set(initialize=sets['carriers'])  # Carriers
        self.model.set_t = RangeSet(1,len(sets['timesteps']))# Timescale
        climate_vars = data.node_data[self.model.set_nodes[1]]['climate_data']['dataframe'].columns.tolist()
        self.model.set_climate_vars = Set(initialize=climate_vars) # climate variables
        def tec_node(model, node):  # Technologies
            try:
                if node in model.set_nodes:
                    return sets['technologies'][node]
            except (KeyError, ValueError):
                print('The nodes in the technology sets do not match the node names. The node \'', node,
                      '\' does not exist.')
                raise
        self.model.set_technologies = Set(self.model.set_nodes, initialize=tec_node)

        # READ IN DATA
        self.data = data

        # Define currency unit
        u.load_definitions_from_strings(['EUR = [currency]'])

    def construct_model(self):
        """
        Constructs model equations, defines objective functions and calculates emissions.

        This function constructs the initial model with all its components as specified in the \
        topology. It adds (1) networks (:func:`~add_networks`), (2) nodes and technologies \
        (:func:`~src.model_construction.construct_nodes.add_nodes` including \
        :func:`~add_technologies`) and (3) links all components with \
        the constructing the energybalance of the optimization problem (:func:`~add_energybalance`).

        The objective is minimized and can be chosen as total annualized costs, total annualized emissions \
        multi-objective (emission-cost pareto front).

        """
        # Todo: implement different options for objective function.

        objective_function = 'cost'

        self.model = add_networks(self.model, self.data)
        self.model = add_nodes(self.model, self.data)
        self.model = add_energybalance(self.model)

        if objective_function == 'cost':
            def cost_objective(obj):
                return sum(self.model.node_blocks[n].cost for n in self.model.set_nodes)
            self.model.objective = Objective(rule=cost_objective, sense=minimize)
        elif objective_function == 'emissions':
            print('to be implemented')
        elif objective_function == 'pareto':
            print('to be implemented')

    def save_model(self, file_path, file_name):
        """
        Saves an instance of the energyhub class to the specified path (using pickel/dill).

        The object can later be loaded using into the work space using :func:`~load_energyhub_instance`

        :param file_path: path to save
        :param file_name: filename
        :return: None
        """
        with open(file_path + '/' + file_name, mode='wb') as file:
            pickle.dump(self, file)

    def print_topology(self):
        print('----- SET OF CARRIERS -----')
        for car in self.model.set_carriers:
            print('- ' + car)
        print('----- NODE DATA -----')
        for node in self.model.set_nodes:
            print('\t -----------------------------------------------------')
            print('\t nodename: '+ node)
            print('\t\ttechnologies installed:')
            for tec in self.model.set_technologies[node]:
                print('\t\t - ' + tec)
            print('\t\taverage demand:')
            for car in self.model.set_carriers:
                avg = round(self.data.demand[node][car].mean(), 2)
                print('\t\t - ' + car + ': ' + str(avg))
            print('\t\taverage of climate data:')
            for ser in self.data.climate_data[node]['dataframe']:
                avg = round(self.data.climate_data[node]['dataframe'][ser].mean(),2)
                print('\t\t - ' + ser + ': ' + str(avg))
        print('----- NETWORK DATA -----')
        for car in self.data.topology['networks']:
            print('\t -----------------------------------------------------')
            print('\t carrier: '+ car)
            for netw in self.data.topology['networks'][car]:
                print('\t\t - ' + netw)
                connection = self.data.topology['networks'][car][netw]['connection']
                for from_node in connection:
                    for to_node in connection[from_node].index:
                        if connection.at[from_node, to_node] == 1:
                            print('\t\t\t' + from_node  + '---' +  to_node)
        # for node in self.model.set_nodes:

    def write_results(self, directory):
        for node_name in self.model.set_nodes:
            # TODO: Add import/export here
            file_name = r'./' + directory + '/' + node_name + '.xlsx'

            # get relevant data
            node_data = self.model.node_blocks[node_name]
            n_carriers = len(self.model.set_carriers)
            n_timesteps = len(self.model.set_t)
            demand = self.data.demand[node_name]

            # Get data - input/output
            input_tecs = dict()
            output_tecs = dict()
            size_tecs = dict()
            for car in self.model.set_carriers:
                input_tecs[car] = pd.DataFrame()
                for tec in node_data.s_techs:
                    if car in node_data.tech_blocks[tec].set_input_carriers:
                        temp = np.zeros((n_timesteps), dtype=float)
                        for t in self.model.set_t:
                            temp[t-1] = node_data.tech_blocks[tec].var_input[t, car].value
                        input_tecs[car][tec] = temp

                output_tecs[car] = pd.DataFrame()
                for tec in node_data.s_techs:
                    if car in node_data.tech_blocks[tec].set_output_carriers:
                        temp = np.zeros((n_timesteps), dtype=float)
                        for t in self.model.set_t:
                            temp[t-1] = node_data.tech_blocks[tec].var_output[t, car].value
                        output_tecs[car][tec] = temp

                for tec in node_data.s_techs:
                    size_tecs[tec] = node_data.tech_blocks[tec].var_size.value

            df = pd.DataFrame(data=size_tecs, index=[0])
            with pd.ExcelWriter(file_name) as writer:
                df.to_excel(writer, sheet_name='size')
                for car in self.model.set_carriers:
                    if car in input_tecs:
                        input_tecs[car].to_excel(writer, sheet_name=car + 'in')
                    if car in output_tecs:
                        output_tecs[car].to_excel(writer, sheet_name=car + 'out')
                writer.save()





            # # Create plot
            # fig, axs = plt.subplots(n_carriers, 2)
            # x = range(1, n_timesteps+1)
            #
            # y = input_tecs['electricity']
            # axs[1, 0].stackplot(x, y)
            #
            # counter_i = 0
            # for car in self.model.set_carriers:
            #     y = input_tecs[car]
            #     print(counter_i)
            #     # axs[counter_i, 0].stackplot(x, y)
            #     counter_i = counter_i + 1


def load_energyhub_instance(file_path):
    """
    Loads an energyhub instance from file.

    :param str file_path: path to previously saved energyhub instance
    :return: energyhub instance
    """

    with open(file_path, mode='rb') as file:
        energyhub = pickle.load(file)
    return energyhub