"""Сохраняет прежний путь импорта управляющих функций herding-атаки."""

from .herding_attack import (
    QuantumLinkFailure,
    Algorithm5LinkParameters,
    algorithm5_link_parameters,
    _random_message_space,
    find_linking_message_quantum,
    execute_algorithm5,
    AttackResult,
    encode_text_prefix_blocks,
    process_prefix_blocks,
    process_prefix_state,
    reconstruct_suffix,
    verify_forged_path,
)

__all__ = ['QuantumLinkFailure', 'Algorithm5LinkParameters', 'algorithm5_link_parameters', '_random_message_space', 'find_linking_message_quantum', 'execute_algorithm5', 'AttackResult', 'encode_text_prefix_blocks', 'process_prefix_blocks', 'process_prefix_state', 'reconstruct_suffix', 'verify_forged_path']
