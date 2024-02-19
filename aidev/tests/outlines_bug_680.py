import interegular


def profile_fsm_construction(pattern_str):
    pat = interegular.parse_pattern(pattern_str)
    fsm = pat.to_fsm()
    reduced = fsm.reduce()


pattern = (
    r'(Path: `Shop\.Service/OrderService\.cs`\n\n\n(\n|[^`].*?\n)*\n\n)?'
    r'(Path: `Shop\.Web/Pages/Order/Archive\.cshtml\.cs`\n\n```cs\n(\n|[^`].*?\n)*```\n\n)?'
    r'(Path: `Shop\.Web/Controllers/OrderController\.cs`\n\n```cs\n(\n|[^`].*?\n)*```\n\n)?'
    r'(Path: `Shop\.Web/Controllers/AccountController\.cs`\n\n```cs\n(\n|[^`].*?\n)*```\n\n)?'
    r'(Path: `Shop\.Data/Enums/OrderBy\.cs`\n\n```cs\n(\n|[^`].*?\n)*```\n\n)?'
    r'(Path: `Shop\.Data/IOrder\.cs`\n\n```cs\n(\n|[^`].*?\n)*```\n\n)?'
    r'(New: `(.*?)`\n\n```([a-z]+)\n(\n|[^`].*?\n)*```\n\n)?'
    r'(New: `(.*?)`\n\n```([a-z]+)\n(\n|[^`].*?\n)*```\n\n)?'
    r'(New: `(.*?)`\n\n```([a-z]+)\n(\n|[^`].*?\n)*```\n\n)?'
    r'END\n'
)

if __name__ == "__main__":
    import pstats
    import cProfile

    cProfile.run('profile_fsm_construction(pattern)', 'profile_stats')
    p = pstats.Stats('profile_stats')
    p.sort_stats('cumtime').print_stats()
