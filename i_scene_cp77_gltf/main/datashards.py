from dataclasses import dataclass
from typing import List, Any

@dataclass
class RigData:
    rig_name: str
    disable_connect: bool
    apose_ms: List[Any]
    apose_ls: List[Any]
    bone_transforms: List[Any]
    bone_parents: List[int]
    bone_names: List[str]
    parts: List[Any]
    track_names: List[Any]
    reference_tracks: List[Any]
    cooking_platform: str
    distance_category_to_lod_map: List[Any]
    ik_setups: List[Any]
    level_of_detail_start_indices: List[Any]
    ragdoll_desc: List[Any]
    ragdoll_names: List[Any]