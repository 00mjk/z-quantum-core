from .interfaces.estimator import Estimator
from .interfaces.backend import QuantumBackend, QuantumSimulator
from .circuit import Circuit
from .measurement import (
    ExpectationValues,
    expectation_values_to_real,
    concatenate_expectation_values,
)
from .hamiltonian import group_comeasureable_terms_greedy
from openfermion import SymbolicOperator, IsingOperator, QubitOperator
from overrides import overrides
import logging
import numpy as np
import pyquil
from typing import Tuple, Optional, Callable

logger = logging.getLogger(__name__)

DECOMPOSITION_METHODS = {
    "greedy": group_comeasureable_terms_greedy,
    "greedy-sorted": lambda qubit_operator: group_comeasureable_terms_greedy(
        qubit_operator, True
    ),
}


def get_decomposition_function(decomposition_method: str) -> Callable:
    """Get a function for Hamiltonian decomposition from it's name.

    Args:
        decomposition_method: The name of the Hamiltonian decomposition method.
    
    Returns:
        A callable that performs the decomposition.
    """

    decomposition_function = DECOMPOSITION_METHODS.get(decomposition_method)
    if decomposition_function is None:
        raise ValueError(
            f"Unrecognized decomposition method {decomposition_method}. Allowed values are {DECOMPOSITION_METHODS.keys()}"
        )
    return decomposition_function


def get_context_selection_circuit(
    term: Tuple[Tuple[int, str], ...]
) -> Tuple[Circuit, IsingOperator]:
    """Get the context selection circuit for measuring the expectation value
    of a Pauli term.

    Args:
        term: The Pauli term, expressed using the OpenFermion convention.
    
    Returns:
        Tuple containing:
        - The context selection circuit.
        - The frame operator
    """

    context_selection_circuit = Circuit()
    operator = IsingOperator(())
    for factor in term:
        if factor[1] == "X":
            context_selection_circuit += Circuit(pyquil.gates.RY(-np.pi / 2, factor[0]))
        elif factor[1] == "Y":
            context_selection_circuit += Circuit(pyquil.gates.RX(np.pi / 2, factor[0]))
        operator *= IsingOperator((factor[0], "Z"))

    return context_selection_circuit, operator


def get_context_selection_circuit_for_group(
    qubit_operator: QubitOperator,
) -> Tuple[Circuit, IsingOperator]:
    """Get the context selection circuit for measuring the expectation value
    of a group of co-measurable Pauli terms.

    Args:
        term: The Pauli term, expressed using the OpenFermion convention.
    
    Returns:
        Tuple containing:
        - The context selection circuit.
        - The frame operator
    """

    context_selection_circuit = Circuit()
    operator = IsingOperator()
    context = []
    for term in qubit_operator.terms:
        term_operator = IsingOperator(())
        for factor in term:
            for existing_factor in context:
                if existing_factor[0] == factor[0] and existing_factor[1] != factor[1]:
                    raise ValueError("Terms are not co-measurable")
            if not factor in context:
                context.append(factor)
            term_operator *= IsingOperator((factor[0], "Z"))
        operator += term_operator*qubit_operator.terms[term]

    for factor in context:
        if factor[1] == "X":
            context_selection_circuit += Circuit(pyquil.gates.RY(-np.pi / 2, factor[0]))
        elif factor[1] == "Y":
            context_selection_circuit += Circuit(pyquil.gates.RX(np.pi / 2, factor[0]))

    return context_selection_circuit, operator


class BasicEstimator(Estimator):
    """An estimator that uses the standard approach to computing expectation values of an operator.
    """

    @overrides
    def get_estimated_expectation_values(
        self,
        backend: QuantumBackend,
        circuit: Circuit,
        target_operator: SymbolicOperator,
        n_samples: Optional[int] = None,
        epsilon: Optional[float] = None,
        delta: Optional[float] = None,
        decomposition_method: str = "greedy-sorted",
    ) -> ExpectationValues:
        """Given a circuit, backend, and target operators, this method produces expectation values 
        for each target operator using the get_expectation_values method built into the provided QuantumBackend. 

        Args:
            backend (QuantumBackend): the backend that will be used to run the circuit
            circuit (Circuit): the circuit that prepares the state.
            target_operator (List[SymbolicOperator]): List of target functions to be estimated.
            n_samples (int): Number of measurements done. 
            epsilon (float): an error term.
            delta (float): a confidence term.
            decomposition_method (str): Which Hamiltonian decomposition method to use. Available options: 'greedy-sorted' (default), 'greedy'

        Returns:
            ExpectationValues: expectation values for each term in the target operator.
        """
        frame_operators = []
        frame_circuits = []
        groups = get_decomposition_function(decomposition_method)(target_operator)
        for group in groups:
            frame_circuit, frame_operator = get_context_selection_circuit_for_group(
                group
            )
            frame_circuits.append(circuit + frame_circuit)
            frame_operators.append(frame_operator)

        if n_samples is not None:
            logger.warning(
                f"""Using n_samples={n_samples} (argument passed to get_estimated_expectation_values). 
                    Ignoring backend.n_samples={backend.n_samples}"""
            )
            saved_n_samples = backend.n_samples
            backend.n_samples = n_samples
            measurements_set = backend.run_circuitset_and_measure(frame_circuits)
            backend.n_samples = saved_n_samples
        else:
            measurements_set = backend.run_circuitset_and_measure(frame_circuits)

        expectation_values_set = []
        for frame_operator, measurements in zip(frame_operators, measurements_set):
            expectation_values_set.append(
                expectation_values_to_real(
                    measurements.get_expectation_values(frame_operator)
                )
            )

        return expectation_values_to_real(
            concatenate_expectation_values(expectation_values_set)
        )


class ExactEstimator(Estimator):
    """An estimator that exactly computes the expectation values of an operator. This estimator must run on a quantum simulator. 
    """

    @overrides
    def get_estimated_expectation_values(
        self,
        backend: QuantumBackend,
        circuit: Circuit,
        target_operator: SymbolicOperator,
        n_samples: Optional[int] = None,
        epsilon: Optional[float] = None,
        delta: Optional[float] = None,
    ) -> ExpectationValues:
        """Given a circuit, backend, and target operators, this method produces expectation values 
        for each target operator using the get_exact_expectation_values method built into the provided QuantumBackend. 

        Args:
            backend (QuantumBackend): the backend that will be used to run the circuit
            circuit (Circuit): the circuit that prepares the state.
            target_operator (List[SymbolicOperator]): List of target functions to be estimated.
            n_samples (int): Number of measurements done on the unknown quantum state. 
            epsilon (float): an error term.
            delta (float): a confidence term.

        Raises:
            AttributeError: If backend is not a QuantumSimulator. 

        Returns:
            ExpectationValues: expectation values for each term in the target operator.
        """
        if isinstance(backend, QuantumSimulator):
            return backend.get_exact_expectation_values(circuit, target_operator)
        else:
            raise AttributeError(
                "To use the ExactEstimator, the backend must be a QuantumSimulator."
            )
