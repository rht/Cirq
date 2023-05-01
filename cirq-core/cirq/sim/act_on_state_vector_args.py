# Copyright 2018 The Cirq Developers
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
"""Objects and methods for acting efficiently on a state vector."""

from typing import Any, Optional, Tuple, TYPE_CHECKING, Type, Union, Dict, List, Sequence

import numpy as np

from cirq import _compat, linalg, protocols, qis, sim
from cirq._compat import proper_repr
from cirq.sim.act_on_args import ActOnArgs, strat_act_on_from_apply_decompose
from cirq.linalg import transformations

if TYPE_CHECKING:
    import cirq


class ActOnStateVectorArgs(ActOnArgs):
    """State and context for an operation acting on a state vector.

    There are two common ways to act on this object:

    1. Directly edit the `target_tensor` property, which is storing the state
        vector of the quantum system as a numpy array with one axis per qudit.
    2. Overwrite the `available_buffer` property with the new state vector, and
        then pass `available_buffer` into `swap_target_tensor_for`.
    """

    @_compat.deprecated_parameter(
        deadline='v0.15',
        fix='Use initial_state instead and specify all the arguments with keywords.',
        parameter_desc='target_tensor and positional arguments',
        match=lambda args, kwargs: 'target_tensor' in kwargs or len(args) != 1,
    )
    def __init__(
        self,
        target_tensor: Optional[np.ndarray] = None,
        available_buffer: Optional[np.ndarray] = None,
        prng: Optional[np.random.RandomState] = None,
        log_of_measurement_results: Optional[Dict[str, List[int]]] = None,
        qubits: Optional[Sequence['cirq.Qid']] = None,
        initial_state: Union[np.ndarray, 'cirq.STATE_VECTOR_LIKE'] = 0,
        dtype: Type[np.number] = np.complex64,
        classical_data: Optional['cirq.ClassicalDataStore'] = None,
    ):
        """Inits ActOnStateVectorArgs.

        Args:
            target_tensor: The state vector to act on, stored as a numpy array
                with one dimension for each qubit in the system. Operations are
                expected to perform inplace edits of this object.
            available_buffer: A workspace with the same shape and dtype as
                `target_tensor`. Used by operations that cannot be applied to
                `target_tensor` inline, in order to avoid unnecessary
                allocations. Passing `available_buffer` into
                `swap_target_tensor_for` will swap it for `target_tensor`.
            qubits: Determines the canonical ordering of the qubits. This
                is often used in specifying the initial state, i.e. the
                ordering of the computational basis states.
            prng: The pseudo random number generator to use for probabilistic
                effects.
            log_of_measurement_results: A mutable object that measurements are
                being recorded into.
            initial_state: The initial state for the simulation in the
                computational basis.
            dtype: The `numpy.dtype` of the inferred state vector. One of
                `numpy.complex64` or `numpy.complex128`. Only used when
                `target_tenson` is None.
            classical_data: The shared classical data container for this
                simulation.
        """
        super().__init__(
            prng=prng,
            qubits=qubits,
            log_of_measurement_results=log_of_measurement_results,
            classical_data=classical_data,
        )
        if target_tensor is None:
            qid_shape = protocols.qid_shape(self.qubits)
            state = qis.to_valid_state_vector(
                initial_state, len(self.qubits), qid_shape=qid_shape, dtype=dtype
            )
            target_tensor = np.reshape(state, qid_shape)
        self.target_tensor = target_tensor

        if available_buffer is None:
            available_buffer = np.empty_like(target_tensor)
        self.available_buffer = available_buffer

    def swap_target_tensor_for(self, new_target_tensor: np.ndarray):
        """Gives a new state vector for the system.

        Typically, the new state vector should be `args.available_buffer` where
        `args` is this `cirq.ActOnStateVectorArgs` instance.

        Args:
            new_target_tensor: The new system state. Must have the same shape
                and dtype as the old system state.
        """
        if new_target_tensor is self.available_buffer:
            self.available_buffer = self.target_tensor
        self.target_tensor = new_target_tensor

    def subspace_index(
        self, axes: Sequence[int], little_endian_bits_int: int = 0, *, big_endian_bits_int: int = 0
    ) -> Tuple[Union[slice, int, 'ellipsis'], ...]:
        """An index for the subspace where the target axes equal a value.

        Args:
            axes: The qubits that are specified by the index bits.
            little_endian_bits_int: The desired value of the qubits at the
                targeted `axes`, packed into an integer. The least significant
                bit of the integer is the desired bit for the first axis, and
                so forth in increasing order. Can't be specified at the same
                time as `big_endian_bits_int`.

                When operating on qudits instead of qubits, the same basic logic
                applies but in a different basis. For example, if the target
                axes have dimension [a:2, b:3, c:2] then the integer 10
                decomposes into [a=0, b=2, c=1] via 7 = 1*(3*2) +  2*(2) + 0.
            big_endian_bits_int: The desired value of the qubits at the
                targeted `axes`, packed into an integer. The most significant
                bit of the integer is the desired bit for the first axis, and
                so forth in decreasing order. Can't be specified at the same
                time as `little_endian_bits_int`.

                When operating on qudits instead of qubits, the same basic logic
                applies but in a different basis. For example, if the target
                axes have dimension [a:2, b:3, c:2] then the integer 10
                decomposes into [a=1, b=2, c=0] via 7 = 1*(3*2) +  2*(2) + 0.

        Returns:
            A value that can be used to index into `target_tensor` and
            `available_buffer`, and manipulate only the part of Hilbert space
            corresponding to a given bit assignment.

        Example:
            If `target_tensor` is a 4 qubit tensor and `axes` is `[1, 3]` and
            then this method will return the following when given
            `little_endian_bits=0b01`:

                `(slice(None), 0, slice(None), 1, Ellipsis)`

            Therefore the following two lines would be equivalent:

                args.target_tensor[args.subspace_index(0b01)] += 1

                args.target_tensor[:, 0, :, 1] += 1
        """
        return linalg.slice_for_qubits_equal_to(
            axes,
            little_endian_qureg_value=little_endian_bits_int,
            big_endian_qureg_value=big_endian_bits_int,
            qid_shape=self.target_tensor.shape,
        )

    def _act_on_fallback_(
        self,
        action: Union['cirq.Operation', 'cirq.Gate'],
        qubits: Sequence['cirq.Qid'],
        allow_decompose: bool = True,
    ) -> bool:
        strats = [
            _strat_act_on_state_vector_from_apply_unitary,
            _strat_act_on_state_vector_from_mixture,
            _strat_act_on_state_vector_from_channel,
        ]
        if allow_decompose:
            strats.append(strat_act_on_from_apply_decompose)

        # Try each strategy, stopping if one works.
        for strat in strats:
            result = strat(action, self, qubits)
            if result is False:
                break  # coverage: ignore
            if result is True:
                return True
            assert result is NotImplemented, str(result)
        raise TypeError(
            "Can't simulate operations that don't implement "
            "SupportsUnitary, SupportsConsistentApplyUnitary, "
            "SupportsMixture or is a measurement: {!r}".format(action)
        )

    def _perform_measurement(self, qubits: Sequence['cirq.Qid']) -> List[int]:
        """Delegates the call to measure the state vector."""
        bits, _ = sim.measure_state_vector(
            self.target_tensor,
            self.get_axes(qubits),
            out=self.target_tensor,
            qid_shape=self.target_tensor.shape,
            seed=self.prng,
        )
        return bits

    def _on_copy(self, target: 'cirq.ActOnStateVectorArgs', deep_copy_buffers: bool = True):
        target.target_tensor = self.target_tensor.copy()
        if deep_copy_buffers:
            target.available_buffer = self.available_buffer.copy()
        else:
            target.available_buffer = self.available_buffer

    def _on_kronecker_product(
        self, other: 'cirq.ActOnStateVectorArgs', target: 'cirq.ActOnStateVectorArgs'
    ):
        target_tensor = transformations.state_vector_kronecker_product(
            self.target_tensor, other.target_tensor
        )
        target.target_tensor = target_tensor
        target.available_buffer = np.empty_like(target_tensor)

    def _on_factor(
        self,
        qubits: Sequence['cirq.Qid'],
        extracted: 'cirq.ActOnStateVectorArgs',
        remainder: 'cirq.ActOnStateVectorArgs',
        validate=True,
        atol=1e-07,
    ):
        axes = self.get_axes(qubits)
        extracted_tensor, remainder_tensor = transformations.factor_state_vector(
            self.target_tensor, axes, validate=validate, atol=atol
        )
        extracted.target_tensor = extracted_tensor
        extracted.available_buffer = np.empty_like(extracted_tensor)
        remainder.target_tensor = remainder_tensor
        remainder.available_buffer = np.empty_like(remainder_tensor)

    @property
    def allows_factoring(self):
        return True

    def _on_transpose_to_qubit_order(
        self, qubits: Sequence['cirq.Qid'], target: 'cirq.ActOnStateVectorArgs'
    ):
        axes = self.get_axes(qubits)
        new_tensor = transformations.transpose_state_vector_to_axis_order(self.target_tensor, axes)
        target.target_tensor = new_tensor
        target.available_buffer = np.empty_like(new_tensor)

    def sample(
        self,
        qubits: Sequence['cirq.Qid'],
        repetitions: int = 1,
        seed: 'cirq.RANDOM_STATE_OR_SEED_LIKE' = None,
    ) -> np.ndarray:
        indices = [self.qubit_map[q] for q in qubits]
        return sim.sample_state_vector(
            self.target_tensor,
            indices,
            qid_shape=tuple(q.dimension for q in self.qubits),
            repetitions=repetitions,
            seed=seed,
        )

    def __repr__(self) -> str:
        return (
            'cirq.ActOnStateVectorArgs('
            f'target_tensor={proper_repr(self.target_tensor)},'
            f' available_buffer={proper_repr(self.available_buffer)},'
            f' qubits={self.qubits!r},'
            f' log_of_measurement_results={proper_repr(self.log_of_measurement_results)})'
        )


def _strat_act_on_state_vector_from_apply_unitary(
    unitary_value: Any,
    args: 'cirq.ActOnStateVectorArgs',
    qubits: Sequence['cirq.Qid'],
) -> bool:
    new_target_tensor = protocols.apply_unitary(
        unitary_value,
        protocols.ApplyUnitaryArgs(
            target_tensor=args.target_tensor,
            available_buffer=args.available_buffer,
            axes=args.get_axes(qubits),
        ),
        allow_decompose=False,
        default=NotImplemented,
    )
    if new_target_tensor is NotImplemented:
        return NotImplemented
    args.swap_target_tensor_for(new_target_tensor)
    return True


def _strat_act_on_state_vector_from_mixture(
    action: Any, args: 'cirq.ActOnStateVectorArgs', qubits: Sequence['cirq.Qid']
) -> bool:
    mixture = protocols.mixture(action, default=None)
    if mixture is None:
        return NotImplemented
    probabilities, unitaries = zip(*mixture)

    index = args.prng.choice(range(len(unitaries)), p=probabilities)
    shape = protocols.qid_shape(action) * 2
    unitary = unitaries[index].astype(args.target_tensor.dtype).reshape(shape)
    linalg.targeted_left_multiply(
        unitary, args.target_tensor, args.get_axes(qubits), out=args.available_buffer
    )
    args.swap_target_tensor_for(args.available_buffer)
    if protocols.is_measurement(action):
        key = protocols.measurement_key_name(action)
        args._classical_data.record_channel_measurement(key, index)
    return True


def _strat_act_on_state_vector_from_channel(
    action: Any, args: 'cirq.ActOnStateVectorArgs', qubits: Sequence['cirq.Qid']
) -> bool:
    kraus_operators = protocols.kraus(action, default=None)
    if kraus_operators is None:
        return NotImplemented

    def prepare_into_buffer(k: int):
        linalg.targeted_left_multiply(
            left_matrix=kraus_tensors[k],
            right_target=args.target_tensor,
            target_axes=args.get_axes(qubits),
            out=args.available_buffer,
        )

    shape = protocols.qid_shape(action)
    kraus_tensors = [e.reshape(shape * 2).astype(args.target_tensor.dtype) for e in kraus_operators]
    p = args.prng.random()
    weight = None
    fallback_weight = 0
    fallback_weight_index = 0
    for index in range(len(kraus_tensors)):
        prepare_into_buffer(index)
        weight = np.linalg.norm(args.available_buffer) ** 2

        if weight > fallback_weight:
            fallback_weight_index = index
            fallback_weight = weight

        p -= weight
        if p < 0:
            break

    assert weight is not None, "No Kraus operators"
    if p >= 0 or weight == 0:
        # Floating point error resulted in a malformed sample.
        # Fall back to the most likely case.
        prepare_into_buffer(fallback_weight_index)
        weight = fallback_weight
        index = fallback_weight_index

    args.available_buffer /= np.sqrt(weight)
    args.swap_target_tensor_for(args.available_buffer)
    if protocols.is_measurement(action):
        key = protocols.measurement_key_name(action)
        args._classical_data.record_channel_measurement(key, index)
    return True
