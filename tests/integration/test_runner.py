"""Test runner for Agent state machine integration tests.

This module provides the TestRunner that orchestrates the test execution,
injecting the mock device via DeviceProtocol and running the Agent through test scenarios.
"""

from pathlib import Path
from typing import Any

from AutoGLM_GUI.device_adapter import DeviceProtocolContext
from AutoGLM_GUI.devices.mock_device import MockDevice
from tests.integration.state_machine import (
    StateMachine,
    TestFailedError,
    load_test_case,
)


class TestRunner:
    """
    Runs Agent integration tests using state machine and mock device.

    The runner:
    1. Loads test case from YAML
    2. Creates MockDevice (DeviceProtocol implementation)
    3. Injects via DeviceProtocolAdapter
    4. Runs the Agent with the test instruction
    5. Verifies the final state
    """

    def __init__(self, test_case_path: str | Path):
        """
        Initialize the test runner.

        Args:
            test_case_path: Path to the YAML test case file
        """
        self.test_case_path = Path(test_case_path)
        self.state_machine: StateMachine | None = None
        self.instruction: str | None = None
        self.max_steps: int = 10
        self.mock_device: MockDevice | None = None

    def load_test_case(self) -> None:
        """Load the test case from YAML file."""
        self.state_machine, self.instruction, self.max_steps = load_test_case(
            self.test_case_path
        )
        self.mock_device = MockDevice("mock_device", self.state_machine)
        print(f"[TestRunner] Loaded test case: {self.test_case_path.name}")
        print(f"[TestRunner] Instruction: {self.instruction}")
        print(f"[TestRunner] Max steps: {self.max_steps}")
        print(f"[TestRunner] States: {list(self.state_machine.states.keys())}")

    def run(
        self,
        model_config: Any = None,
        agent_config: Any = None,
    ) -> dict[str, Any]:
        """
        Run the test.

        Args:
            model_config: Optional ModelConfig override
            agent_config: Optional AgentConfig override

        Returns:
            Test result dictionary
        """
        if self.state_machine is None:
            self.load_test_case()

        assert self.state_machine is not None
        assert self.mock_device is not None
        assert self.instruction is not None

        state_machine = self.state_machine
        mock_device = self.mock_device
        instruction = self.instruction
        # Import here to avoid circular imports
        from AutoGLM_GUI.agents.glm.agent import GLMAgent
        from AutoGLM_GUI.config import AgentConfig, ModelConfig

        # Create configs if not provided
        if model_config is None:
            from AutoGLM_GUI.config_manager import config_manager

            # Load config from both file and environment variables
            # Priority: CLI > ENV > File > Default
            config_manager.load_env_config()  # Load from environment variables (GitHub Secrets)
            config_manager.load_file_config()  # Load from config file
            effective_config = config_manager.get_effective_config()

            model_config = ModelConfig(
                base_url=effective_config.base_url,
                api_key=effective_config.api_key,
                model_name=effective_config.model_name,
            )

        if agent_config is None:
            agent_config = AgentConfig(
                max_steps=self.max_steps,
                device_id="mock_device",
                verbose=True,
            )
        else:
            # Override max_steps from test case
            agent_config.max_steps = self.max_steps

        print("\n" + "=" * 60)
        print("[TestRunner] Starting test execution...")
        print("=" * 60 + "\n")

        with DeviceProtocolContext(
            get_device=lambda _: mock_device,
            default_device_id="mock_device",
        ):
            try:
                # Create and run agent
                agent = GLMAgent(
                    model_config=model_config,
                    agent_config=agent_config,
                    device=mock_device,
                )

                result_message = agent.run(instruction)

                if result_message == "Max steps reached":
                    state_machine.failure_reason = (
                        f"Agent exceeded max steps ({self.max_steps}) without completing task. "
                        f"Final state: {state_machine.current_state_id}"
                    )
                    print(f"\n[TestRunner] Test FAILED: {state_machine.failure_reason}")
                else:
                    state_machine.handle_finish(result_message)

            except TestFailedError as e:
                print(f"\n[TestRunner] Test failed with error: {e}")

            except Exception as e:
                state_machine.failure_reason = f"Unexpected error: {e}"
                print(f"\n[TestRunner] Unexpected error: {e}")
                import traceback

                traceback.print_exc()

        result = state_machine.get_result()
        self._print_result(result)

        return result

    def _print_result(self, result: dict[str, Any]) -> None:
        """Print test result summary."""
        print("\n" + "=" * 60)
        print("TEST RESULT")
        print("=" * 60)
        print(f"  Status: {'PASSED' if result['passed'] else 'FAILED'}")
        print(f"  Final State: {result['final_state']}")
        print(f"  State History: {' -> '.join(result['state_history'])}")
        print(f"  Total Actions: {result['action_count']}")

        if result["failure_reason"]:
            print(f"  Failure Reason: {result['failure_reason']}")

        print("\n  Action History:")
        for i, action in enumerate(result["action_history"], 1):
            action_type = action["action"]
            if action_type == "tap":
                print(
                    f"    {i}. tap({action['x']}, {action['y']}) "
                    f"in state '{action['state']}'"
                )
            elif action_type == "swipe":
                print(
                    f"    {i}. swipe({action['start_x']}, {action['start_y']} -> "
                    f"{action['end_x']}, {action['end_y']}) in state '{action['state']}'"
                )
            elif action_type == "finish":
                print(
                    f"    {i}. finish('{action.get('message', '')}') "
                    f"in state '{action['state']}'"
                )

        print("=" * 60 + "\n")


def run_test(test_case_path: str | Path) -> dict[str, Any]:
    """
    Convenience function to run a single test.

    Args:
        test_case_path: Path to the YAML test case file

    Returns:
        Test result dictionary
    """
    runner = TestRunner(test_case_path)
    return runner.run()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m tests.integration.test_runner <test_case.yaml>")
        sys.exit(1)

    result = run_test(sys.argv[1])
    sys.exit(0 if result["passed"] else 1)
