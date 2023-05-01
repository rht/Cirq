# Copyright 2019 The Cirq Developers
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

import numpy as np
import pytest

import cirq
import cirq_google as cg


class FakeDevice(cirq.Device):
    def __init__(self):
        pass


def test_invalid_input():
    with cirq.testing.assert_deprecated(
        'Use `cirq.optimize_for_target_gateset', deadline='v0.16', count=1
    ):
        with pytest.raises(ValueError):
            q0, q1 = cirq.LineQubit.range(2)
            circuit = cirq.Circuit(
                cirq.CZ(q0, q1), cirq.X(q0) ** 0.2, cirq.Z(q1) ** 0.2, cirq.measure(q0, q1, key='m')
            )
            _ = cg.optimized_for_sycamore(circuit, optimizer_type='for_tis_100')


def test_tabulation():
    q0, q1 = cirq.LineQubit.range(2)
    u = cirq.testing.random_special_unitary(4, random_state=np.random.RandomState(52))
    circuit = cirq.Circuit(cirq.MatrixGate(u).on(q0, q1))
    np.testing.assert_allclose(u, cirq.unitary(circuit))

    with cirq.testing.assert_deprecated(
        'Use `cirq.optimize_for_target_gateset', deadline='v0.16', count=2
    ):
        circuit2 = cg.optimized_for_sycamore(circuit, optimizer_type='sycamore')
        cirq.testing.assert_allclose_up_to_global_phase(u, cirq.unitary(circuit2), atol=1e-5)
        assert len(circuit2) == 13
        # Note this is run on every commit, so it needs to be relatively quick.
        # This requires us to use relatively loose tolerances
        circuit3 = cg.optimized_for_sycamore(
            circuit, optimizer_type='sycamore', tabulation_resolution=0.1
        )
        cirq.testing.assert_allclose_up_to_global_phase(
            u, cirq.unitary(circuit3), rtol=1e-1, atol=1e-1
        )
        assert len(circuit3) == 7


def test_no_tabulation():
    circuit = cirq.Circuit(cirq.X(cirq.LineQubit(0)))

    with cirq.testing.assert_deprecated(
        'Use `cirq.optimize_for_target_gateset', deadline='v0.16', count=3
    ):
        with pytest.raises(NotImplementedError):
            cg.optimized_for_sycamore(
                circuit, optimizer_type='sqrt_iswap', tabulation_resolution=0.01
            )

        with pytest.raises(NotImplementedError):
            cg.optimized_for_sycamore(circuit, optimizer_type='xmon', tabulation_resolution=0.01)

        with pytest.raises(NotImplementedError):
            cg.optimized_for_sycamore(
                circuit, optimizer_type='xmon_partial_cz', tabulation_resolution=0.01
            )


@pytest.mark.parametrize(
    'optimizer_type, two_qubit_gate_type',
    [('sycamore', cg.SycamoreGate), ('sqrt_iswap', cirq.ISwapPowGate), ('xmon', cirq.CZPowGate)],
)
def test_circuit_operation_conversion(optimizer_type, two_qubit_gate_type):
    q0, q1 = cirq.LineQubit.range(2)
    subcircuit = cirq.FrozenCircuit(cirq.X(q0), cirq.SWAP(q0, q1))
    circuit = cirq.Circuit(cirq.CircuitOperation(subcircuit))
    with cirq.testing.assert_deprecated(
        'Use `cirq.optimize_for_target_gateset', deadline='v0.16', count=2
    ):
        converted_circuit = cg.optimized_for_sycamore(circuit, optimizer_type=optimizer_type)
        # Verify that the CircuitOperation was preserved.
        ops = list(converted_circuit.all_operations())
        assert isinstance(ops[0], cirq.CircuitOperation)
        # Verify that the contents of the CircuitOperation were optimized.
        converted_subcircuit = cg.optimized_for_sycamore(
            subcircuit.unfreeze(), optimizer_type=optimizer_type
        )
        assert len(
            [*converted_subcircuit.findall_operations_with_gate_type(two_qubit_gate_type)]
        ) == len([*ops[0].circuit.findall_operations_with_gate_type(two_qubit_gate_type)])
        cirq.testing.assert_circuits_with_terminal_measurements_are_equivalent(
            ops[0].circuit, converted_subcircuit, atol=1e-8
        )
        cirq.testing.assert_circuits_with_terminal_measurements_are_equivalent(
            circuit, converted_circuit, atol=1e-8
        )
