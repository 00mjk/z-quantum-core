from zquantum.core.utils import ValueEstimate

from .interfaces.backend import QuantumBackend
from .interfaces.ansatz import Ansatz
from .interfaces.estimator import Estimator
from .circuit import combine_ansatz_params
from .estimator import BasicEstimator
from typing import Optional
import numpy as np
from openfermion import SymbolicOperator


class AnsatzBasedCostFunction:
    """Cost function used for evaluating given operator using given ansatz.

    Args:
        target_operator (openfermion.QubitOperator): operator to be evaluated
        ansatz (zquantum.core.interfaces.ansatz.Ansatz): ansatz used to evaluate cost function
        backend (zquantum.core.interfaces.backend.QuantumBackend): backend used for evaluation
        estimator: (zquantum.core.interfaces.estimator.Estimator) = estimator used to compute expectation value of target operator
        n_samples (int): number of samples (i.e. measurements) to be used in the estimator. 
        epsilon (float): an additive/multiplicative error term. The cost function should be computed to within this error term. 
        delta (float): a confidence term. If theoretical upper bounds are known for the estimation technique, 
            the final estimate should be within the epsilon term, with probability 1 - delta.
        fixed_parameters (np.ndarray): values for the circuit parameters that should be fixed. 

    Params:
        target_operator (openfermion.QubitOperator): see Args
        ansatz (zquantum.core.interfaces.ansatz.Ansatz): see Args
        backend (zquantum.core.interfaces.backend.QuantumBackend): see Args
        estimator: (zquantum.core.interfaces.estimator.Estimator) = see Args 
        n_samples (int): see Args
        epsilon (float): see Args
        delta (float): see Args
        fixed_parameters (np.ndarray): see Args
    """

    def __init__(
        self,
        target_operator: SymbolicOperator,
        ansatz: Ansatz,
        backend: QuantumBackend,
        estimator: Estimator = None,
        n_samples: Optional[int] = None,
        epsilon: Optional[float] = None,
        delta: Optional[float] = None,
        fixed_parameters: Optional[np.ndarray] = None,
    ):
        self.target_operator = target_operator
        self.ansatz = ansatz
        self.backend = backend
        if estimator is None:
            self.estimator = BasicEstimator()
        else:
            self.estimator = estimator
        self.n_samples = n_samples
        self.epsilon = epsilon
        self.delta = delta
        self.fixed_parameters = fixed_parameters

    def __call__(self, parameters: np.ndarray) -> ValueEstimate:
        """Evaluates the value of the cost function for given parameters.

        Args:
            parameters: parameters for which the evaluation should occur.

        Returns:
            value: cost function value for given parameters.
        """
        if self.fixed_parameters is not None:
            parameters = combine_ansatz_params(self.fixed_parameters, parameters)
        circuit = self.ansatz.get_executable_circuit(parameters)
        expectation_values = self.estimator.get_estimated_expectation_values(
            self.backend,
            circuit,
            self.target_operator,
            n_samples=self.n_samples,
            epsilon=self.epsilon,
            delta=self.delta,
        )
        return ValueEstimate(np.sum(expectation_values.values))
