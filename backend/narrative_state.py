"""Cross-record consequences for explicitly settled outcomes, not free-text guesses."""


def record_npc_death(state, target, evidence):
    """Keep historical membership; mark known identities unavailable everywhere."""
    matches = []
    wanted = target.casefold()
    for field in ('npc_memories', 'contacts'):
        for name, row in (state.get(field) or {}).items() if isinstance(state.get(field), dict) else []:
            if str(name).casefold() == wanted and isinstance(row, dict): matches.append(row)
    for row in state.get('companions', []) if isinstance(state.get('companions'), list) else []:
        if isinstance(row, dict) and str(row.get('name', '')).casefold() == wanted: matches.append(row)
    for group in (state.get('organizations') or {}).values() if isinstance(state.get('organizations'), dict) else []:
        if not isinstance(group, dict) or not isinstance(group.get('members'), dict): continue
        for name, row in group['members'].items():
            if str(name).casefold() == wanted and isinstance(row, dict):
                matches.append(row)
                row['membership_status'] = 'dead'
    for row in matches:
        row.update(status='dead', alive=False, death_reason=evidence)
    return bool(matches)
