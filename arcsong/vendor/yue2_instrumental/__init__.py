"""YuE2's own Vocal → Ins score conversion, vendored unchanged except for imports.

Source: github.com/multimodal-art-projection/YuE, skills/yue2-music/instrumental/scripts
(compile_score.py, instrumentalize.py, common.py) at commit 0495110587a4, MIT licence (LICENSE
here). Its abc_tools.py parses identically to mlx-Yue's `lyra.music_tools.abc_tools`, which is
used instead.
"""

from .instrumentalize import convert_score

__all__ = ["convert_score"]
