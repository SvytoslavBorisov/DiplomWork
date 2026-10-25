"""Сохраняет прежний путь импорта управляющих функций herding-атаки."""

from .herding_attack import (
    AttackResult,
    encode_text_prefix_blocks,
    process_prefix_blocks,
    process_prefix_state,
    reconstruct_suffix,
    find_linking_message,
    _leaf_sigma,
    verify_forged_path,
    execute_attack,
)

__all__ = ['AttackResult', 'encode_text_prefix_blocks', 'process_prefix_blocks', 'process_prefix_state', 'reconstruct_suffix', 'find_linking_message', '_leaf_sigma', 'verify_forged_path', 'execute_attack']
