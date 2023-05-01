# Copyright 2020 The Cirq Developers
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING, Union

import numpy as np

from cirq import _compat, value, ops, protocols
from cirq.sim.clifford import stabilizer_state_ch_form
from cirq.sim.clifford.act_on_stabilizer_args import ActOnStabilizerArgs

if TYPE_CHECKING:
    import cirq


class ActOnStabilizerCHFormArgs(
    ActOnStabilizerArgs[stabilizer_state_ch_form.StabilizerStateChForm]
):
    """Wrapper around a stabilizer state in CH form for the act_on protocol."""

    @_compat.deprecated_parameter(
        deadline='v0.15',
        fix='Specify all the arguments with keywords, use initial_state instead of state.',
        parameter_desc='positional arguments',
        match=lambda args, kwargs: len(args) != 1 or 'state' in kwargs,
    )
    def __init__(
        self,
        state: Optional['cirq.StabilizerStateChForm'] = None,
        prng: Optional[np.random.RandomState] = None,
        log_of_measurement_results: Optional[Dict[str, Any]] = None,
        qubits: Optional[Sequence['cirq.Qid']] = None,
        initial_state: Union[int, 'cirq.StabilizerStateChForm'] = 0,
        classical_data: Optional['cirq.ClassicalDataStore'] = None,
    ):
        """Initializes with the given state and the axes for the operation.

        Args:
            state: The StabilizerStateChForm to act on. Operations are expected
                to perform inplace edits of this object.
            qubits: Determines the canonical ordering of the qubits. This
                is often used in specifying the initial state, i.e. the
                ordering of the computational basis states.
            prng: The pseudo random number generator to use for probabilistic
                effects.
            log_of_measurement_results: A mutable object that measurements are
                being recorded into.
            initial_state: The initial state for the simulation. This can be a
                full CH form passed by reference which will be modified inplace,
                or a big-endian int in the computational basis. If the state is
                an integer, qubits must be provided in order to determine
                array sizes.
            classical_data: The shared classical data container for this
                simulation.

        Raises:
            ValueError: If initial state is an integer but qubits are not
                provided.
        """
        initial_state = state or initial_state
        if isinstance(initial_state, int):
            if qubits is None:
                raise ValueError('Must specify qubits if initial state is integer')
            initial_state = stabilizer_state_ch_form.StabilizerStateChForm(
                len(qubits), initial_state
            )
        super().__init__(
            state=initial_state,
            prng=prng,
            qubits=qubits,
            log_of_measurement_results=log_of_measurement_results,
            classical_data=classical_data,
        )

    def _perform_measurement(self, qubits: Sequence['cirq.Qid']) -> List[int]:
        """Returns the measurement from the stabilizer state form."""
        return [self.state._measure(self.qubit_map[q], self.prng) for q in qubits]

    def _on_copy(self, target: 'ActOnStabilizerCHFormArgs', deep_copy_buffers: bool = True):
        target._state = self.state.copy()

    def _on_kronecker_product(
        self, other: 'cirq.ActOnStabilizerCHFormArgs', target: 'cirq.ActOnStabilizerCHFormArgs'
    ):
        target._state = self.state.kron(other.state)

    def _on_transpose_to_qubit_order(
        self, qubits: Sequence['cirq.Qid'], target: 'cirq.ActOnStabilizerCHFormArgs'
    ):
        axes = [self.qubit_map[q] for q in qubits]
        target._state = self.state.reindex(axes)

    def sample(
        self,
        qubits: Sequence['cirq.Qid'],
        repetitions: int = 1,
        seed: 'cirq.RANDOM_STATE_OR_SEED_LIKE' = None,
    ) -> np.ndarray:
        measurements = value.ClassicalDataDictionaryStore()
        prng = value.parse_random_state(seed)
        for i in range(repetitions):
            op = ops.measure(*qubits, key=str(i))
            state = self.state.copy()
            ch_form_args = ActOnStabilizerCHFormArgs(
                classical_data=measurements,
                prng=prng,
                qubits=self.qubits,
                initial_state=state,
            )
            protocols.act_on(op, ch_form_args)
        return np.array(list(measurements.measurements.values()), dtype=bool)
