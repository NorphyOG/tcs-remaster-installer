"""Automatic overlays for the checked Classic Plus recipe.

An overlay selects one complete author file. It is not a binary merge or a
gameplay compatibility claim. Unknown module combinations remain conflicts.
"""
from __future__ import annotations

from pathlib import PurePosixPath


# The authors install Infinities after Modern Overhaul and the matching patches
# after their parent add-ons. This rule is limited to their character/art files.
AUTHOR_ASSETS = {'.gsc', '.ghg', '.dds', '.tga', '.png', '.bmp'}
AUTHOR_CHAINS = (
    ('infinities', {'modern-overhaul', 'infinities'}, {'modern-overhaul'}),
    ('infinities-al-patch', {'modern-overhaul', 'additional-levels-mo', 'infinities', 'infinities-al-patch'}, {'modern-overhaul', 'additional-levels-mo', 'infinities'}),
    ('infinities-vader-patch', {'modern-overhaul', 'ep3-additions', 'infinities', 'infinities-vader-patch'}, {'modern-overhaul', 'ep3-additions', 'infinities'}),
)

# These text/script overlays were checked against the imported 0.4.0 recipe
# files. The Additional Levels build targets Modern Overhaul specifically. A
# changed file hash must return to review rather than silently inherit the rule.
PINNED = {
    'audio/music.cfg': (('modern-overhaul', 'additional-levels-mo'), ('f49b7f1e49d89f49de22b794cc06e245c64a9abbc26f56d1b52afb377b1f9462', '316bcb05270ff4740e74dd98ef21c240e7dd57e5f95a95e4c357c744ea49f0dc'), 1),
    'chars/collection.txt': (('modern-overhaul', 'additional-levels-mo'), ('23ca921e019c0cd36a17c0f47b342c40009fbbea9e157357040294024dc8d548', '3065e52b0564b52cb41c030161c43fb31abcbf23329541e906277f0855357eb1'), 1),
    'chars/macewindu/macewindu.txt': (('modern-overhaul', 'additional-levels-mo'), ('6b7a7b495ee630f1a0a731436c4e5781db486db1d02377c755cf934c2903ea1e', 'ec16a132373179744084476e9d4e07e918aadadc8487a1e8cf3fe66ed95f6bdb'), 1),
    'levels/episode_iii/temple/temple.txt': (('modern-overhaul', 'additional-levels-mo'), ('91b4f086b0041f6debc4e13eab8aebf738c7ed6522d6469fcb83630b1fbed929', '4dcee6a92a6212c2d26ff63c23c47151165c3a3c975d710aedcb62c3cd306ab2'), 1),
    'levels/episode_iii/temple/temple_b/ai/temple_b.ai2': (('modern-overhaul', 'additional-levels-mo'), ('bda32687c5847cbfeb1d4f7f1e1561af69375382cec2b3e81ff95e9057baeddd', 'de1d22837e8cbb674c698470b12b15513a4b44b856bf76852a240f7be57b24c1'), 1),
    'levels/episode_iii/temple/temple_c/ai/temple_c.ai2': (('modern-overhaul', 'additional-levels-mo'), ('9ff6e127664a1f28f909e0b847eebc7fccc0c684ad9c85ee75561012461fe797', '4d5de41c92f5580d00543aa6ee3df8c79128a37789f4f1e01da669ce4e2f649c'), 1),
    'levels/episode_iii/vader/vader.txt': (('modern-overhaul', 'ep3-additions'), ('fe27dc8f64c8334eeb3e63c71e08e636076d09b187880a300599537c043f8a5f', 'f65cde4f487863ae298d8fb3ac0d51501dc01cc8bb54dbb7b0f7ac86d635801a'), 1),
    'stuff/text/english.txt': (('modern-overhaul', 'additional-levels-mo'), ('e002086e1d333c599a8e287f4c51fe2ab07d33f056639dad08f6526c3463b2ab', 'cd00ff2e767bc23f0d8e62ee4ee13c7e705d7ef1fef83c447e211a84a9ba897f'), 1),
    # Both Additional Levels changes are present in the Episode III variant:
    # CHARS.TXT is a strict byte prefix; E3ENDING.TXT keeps the new trooper and
    # additionally changes the Obi-Wan cutscene model. Pin all three inputs.
    'chars/chars.txt': (('modern-overhaul', 'ep3-additions', 'additional-levels-mo'), ('6f72217701ecb8667174505becd0c82a66c52f6a0bbca369ba3e34be132ef859', '095cc3755e1aee8a4c067b74cadc3a7662948ed9312c032b0e3a0ed57a2d45fb', 'efd5da606fcc890cd57b4006ee158ea802a365d6cc2005db27b0bbac5cb3121d'), 1),
    'levels/episode_iii/ending/e3ending.txt': (('modern-overhaul', 'ep3-additions', 'additional-levels-mo'), ('25c59d3125578c405ab15ef237e46ef147c9432b067a6c77ffa7f189c16f2522', '217a80e1e7f47f1deaa67c34e80d90a32b912725664f401fa448553716530c53', '2383f556948c9b75ecf4e28a5f6510d0621d88dcb72cfccbd5de7397e507ab28'), 1),
}


def choose_overlay(path: str, versions: list[dict]) -> tuple[int, str] | None:
    """Return the selected version index and auditable reason, or no decision."""
    key = path.casefold()
    modules = tuple(v['module'] for v in versions)
    hashes = tuple(v['sha256'] for v in versions)
    pinned = PINNED.get(key)
    if pinned and (modules, hashes) == pinned[:2]:
        return pinned[2], 'Hashgebundene Rezept-Überlagerung; vollständige Autorendatei, kein Merge.'

    if key.split('/')[0] not in {'chars', 'stuff'} or PurePosixPath(key).suffix not in AUTHOR_ASSETS:
        return None
    providers = set(modules)
    for last, allowed, required in AUTHOR_CHAINS:
        if modules[-1] == last and providers & required and providers <= allowed:
            return len(versions)-1, 'Autoren-Reihenfolge des bestätigten Modrezepts; vollständige Datei ersetzt, kein Binär-Merge.'
    return None
