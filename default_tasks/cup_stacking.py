"""Cup Stacking — default eval task shipped with the worker.

Builds on the simulator's `CupStackingEnvCfg` (sim/packages/simulator/src/simulator/
tasks/cup_stacking/). Edit it in the UI (Admin → Tasks): override anything in
__post_init__ below — object spawn ranges, lighting, success thresholds.
Episodes and episode length come from the UI (Settings, or this task's
overrides), not from this file.
"""
import gymnasium as gym
from isaaclab.utils import configclass

from simulator.tasks.cup_stacking.cup_stacking_env_cfg import CupStackingEnvCfg

# Gym id this file registers. Keep "SingleArm" in it: rollout.py reads
# the robot from the id.
TASK_ID = "Eval-CupStacking-SingleArm-v0"


@configclass
class EvalEnvCfg(CupStackingEnvCfg):
    def __post_init__(self) -> None:
        super().__post_init__()
        # Examples of what a school might tighten or vary:
        # self.terminations.success.params["height_threshold"] = 0.08
        # self.terminations.success.params["x_range"] = (-0.03, 0.03)
        pass


gym.register(
    id=TASK_ID,
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={"env_cfg_entry_point": f"{__name__}:EvalEnvCfg"},
)
