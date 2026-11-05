"""Cutlery Arrangement — default eval task shipped with the worker.

Builds on the simulator's `CutleryArrangementEnvCfg` (sim/packages/simulator/src/simulator/
tasks/cutlery_arrangement/). Edit it in the UI (Admin → Tasks): override anything in
__post_init__ below — object spawn ranges, lighting, success thresholds.
Episodes and episode length come from the UI (Settings, or this task's
overrides), not from this file.
"""
import gymnasium as gym
from isaaclab.utils import configclass

from simulator.tasks.cutlery_arrangement.cutlery_arrangement_env_cfg import CutleryArrangementEnvCfg

# Gym id this file registers. Keep "SingleArm" in it: rollout.py reads
# the robot from the id.
TASK_ID = "Eval-CutleryArrangement-SingleArm-v0"


@configclass
class EvalEnvCfg(CutleryArrangementEnvCfg):
    def __post_init__(self) -> None:
        super().__post_init__()
        # Examples of what a school might tighten or vary:
        # self.task_description = "place the fork on the left and the knife on the right of the plate."
        pass


gym.register(
    id=TASK_ID,
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={"env_cfg_entry_point": f"{__name__}:EvalEnvCfg"},
)
