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
"""An immutable version of the Circuit data structure."""
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Callable,
    FrozenSet,
    Iterable,
    Iterator,
    Optional,
    Sequence,
    Tuple,
    Union,
)
import re

from cirq.circuits import AbstractCircuit, Alignment, Circuit
from cirq.circuits.insert_strategy import InsertStrategy
from cirq.type_workarounds import NotImplementedType

import numpy as np

from cirq import _compat, devices, ops, protocols


if TYPE_CHECKING:
    import cirq


_DEVICE_DEP_MESSAGE = 'Attaching devices to circuits will no longer be supported.'


class FrozenCircuit(AbstractCircuit, protocols.SerializableByKey):
    """An immutable version of the Circuit data structure.

    FrozenCircuits are immutable (and therefore hashable), but otherwise behave
    identically to regular Circuits. Conversion between the two is handled with
    the `freeze` and `unfreeze` methods from AbstractCircuit.
    """

    @_compat.deprecated_parameter(
        deadline='v0.15',
        fix=_DEVICE_DEP_MESSAGE,
        parameter_desc='device',
        match=lambda args, kwargs: 'device' in kwargs,
    )
    def __init__(
        self,
        *contents: 'cirq.OP_TREE',
        strategy: 'cirq.InsertStrategy' = InsertStrategy.EARLIEST,
        device: 'cirq.Device' = devices.UNCONSTRAINED_DEVICE,
    ) -> None:
        """Initializes a frozen circuit.

        Args:
            contents: The initial list of moments and operations defining the
                circuit. You can also pass in operations, lists of operations,
                or generally anything meeting the `cirq.OP_TREE` contract.
                Non-moment entries will be inserted according to the specified
                insertion strategy.
            strategy: When initializing the circuit with operations and moments
                from `contents`, this determines how the operations are packed
                together.
            device: Hardware that the circuit should be able to run on.
        """
        if device == devices.UNCONSTRAINED_DEVICE:
            base = Circuit(contents, strategy=strategy)
        else:
            with _compat.block_overlapping_deprecation(re.escape(_DEVICE_DEP_MESSAGE)):
                base = Circuit(contents, strategy=strategy, device=device)

        self._moments = tuple(base.moments)
        self._device = base._device

        # These variables are memoized when first requested.
        self._num_qubits: Optional[int] = None
        self._unitary: Optional[Union[np.ndarray, NotImplementedType]] = None
        self._qid_shape: Optional[Tuple[int, ...]] = None
        self._all_qubits: Optional[FrozenSet['cirq.Qid']] = None
        self._all_operations: Optional[Tuple[ops.Operation, ...]] = None
        self._has_measurements: Optional[bool] = None
        self._all_measurement_key_objs: Optional[AbstractSet['cirq.MeasurementKey']] = None
        self._are_all_measurements_terminal: Optional[bool] = None
        self._control_keys: Optional[FrozenSet['cirq.MeasurementKey']] = None

    @property
    def moments(self) -> Sequence['cirq.Moment']:
        return self._moments

    @property  # type: ignore
    @_compat.deprecated(
        deadline='v0.15',
        fix=_DEVICE_DEP_MESSAGE,
    )
    def device(self) -> devices.Device:
        return self._device

    def __hash__(self):
        return hash((self.moments, self._device))

    # Memoized methods for commonly-retrieved properties.

    def _num_qubits_(self) -> int:
        if self._num_qubits is None:
            self._num_qubits = len(self.all_qubits())
        return self._num_qubits

    def _qid_shape_(self) -> Tuple[int, ...]:
        if self._qid_shape is None:
            self._qid_shape = super()._qid_shape_()
        return self._qid_shape

    def _unitary_(self) -> Union[np.ndarray, NotImplementedType]:
        if self._unitary is None:
            self._unitary = super()._unitary_()
        return self._unitary

    def _is_measurement_(self) -> bool:
        if self._has_measurements is None:
            self._has_measurements = protocols.is_measurement(self.unfreeze())
        return self._has_measurements

    def all_qubits(self) -> FrozenSet['cirq.Qid']:
        if self._all_qubits is None:
            self._all_qubits = super().all_qubits()
        return self._all_qubits

    def all_operations(self) -> Iterator['cirq.Operation']:
        if self._all_operations is None:
            self._all_operations = tuple(super().all_operations())
        return iter(self._all_operations)

    def has_measurements(self) -> bool:
        if self._has_measurements is None:
            self._has_measurements = super().has_measurements()
        return self._has_measurements

    def all_measurement_key_objs(self) -> AbstractSet['cirq.MeasurementKey']:
        if self._all_measurement_key_objs is None:
            self._all_measurement_key_objs = super().all_measurement_key_objs()
        return self._all_measurement_key_objs

    def _measurement_key_objs_(self) -> AbstractSet['cirq.MeasurementKey']:
        return self.all_measurement_key_objs()

    def _control_keys_(self) -> FrozenSet['cirq.MeasurementKey']:
        if self._control_keys is None:
            self._control_keys = super()._control_keys_()
        return self._control_keys

    def are_all_measurements_terminal(self) -> bool:
        if self._are_all_measurements_terminal is None:
            self._are_all_measurements_terminal = super().are_all_measurements_terminal()
        return self._are_all_measurements_terminal

    # End of memoized methods.

    def all_measurement_key_names(self) -> AbstractSet[str]:
        return {str(key) for key in self.all_measurement_key_objs()}

    def _measurement_key_names_(self) -> AbstractSet[str]:
        return self.all_measurement_key_names()

    def __add__(self, other) -> 'cirq.FrozenCircuit':
        return (self.unfreeze() + other).freeze()

    def __radd__(self, other) -> 'cirq.FrozenCircuit':
        return (other + self.unfreeze()).freeze()

    # Needed for numpy to handle multiplication by np.int64 correctly.
    __array_priority__ = 10000

    # TODO: handle multiplication / powers differently?
    def __mul__(self, other) -> 'cirq.FrozenCircuit':
        return (self.unfreeze() * other).freeze()

    def __rmul__(self, other) -> 'cirq.FrozenCircuit':
        return (other * self.unfreeze()).freeze()

    def __pow__(self, other) -> 'cirq.FrozenCircuit':
        try:
            return (self.unfreeze() ** other).freeze()
        except:
            return NotImplemented

    def _with_sliced_moments(self, moments: Iterable['cirq.Moment']) -> 'FrozenCircuit':
        if self._device == devices.UNCONSTRAINED_DEVICE:
            new_circuit = FrozenCircuit()
        else:
            new_circuit = FrozenCircuit(device=self._device)
        new_circuit._moments = tuple(moments)
        return new_circuit

    @_compat.deprecated(
        deadline='v0.15',
        fix=_DEVICE_DEP_MESSAGE,
    )
    def with_device(
        self,
        new_device: 'cirq.Device',
        qubit_mapping: Callable[['cirq.Qid'], 'cirq.Qid'] = lambda e: e,
    ) -> 'FrozenCircuit':
        with _compat.block_overlapping_deprecation(re.escape(_DEVICE_DEP_MESSAGE)):
            return self.unfreeze().with_device(new_device, qubit_mapping).freeze()

    def _resolve_parameters_(
        self, resolver: 'cirq.ParamResolver', recursive: bool
    ) -> 'cirq.FrozenCircuit':
        return self.unfreeze()._resolve_parameters_(resolver, recursive).freeze()

    def tetris_concat(
        *circuits: 'cirq.AbstractCircuit', align: Union['cirq.Alignment', str] = Alignment.LEFT
    ) -> 'cirq.FrozenCircuit':
        return AbstractCircuit.tetris_concat(*circuits, align=align).freeze()

    tetris_concat.__doc__ = AbstractCircuit.tetris_concat.__doc__

    def zip(
        *circuits: 'cirq.AbstractCircuit', align: Union['cirq.Alignment', str] = Alignment.LEFT
    ) -> 'cirq.FrozenCircuit':
        return AbstractCircuit.zip(*circuits, align=align).freeze()

    zip.__doc__ = AbstractCircuit.zip.__doc__

    def to_op(self) -> 'cirq.CircuitOperation':
        """Creates a CircuitOperation wrapping this circuit."""
        from cirq.circuits import CircuitOperation

        return CircuitOperation(self)
