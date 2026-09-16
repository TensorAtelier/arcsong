from spike.env import model_servers_from_ps

PS_OUTPUT = """\
  101  204800 /Applications/Ollama.app/Contents/Resources/ollama serve
  202    1024 /bin/zsh -l
  303  512000 /Applications/LM Studio.app/Contents/MacOS/LM Studio
  404  409600 /Users/me/image_gen/ComfyUI/.venv/bin/python main.py --listen
  505    2048 grep ollama
"""


def test_model_servers_are_detected_from_the_process_list():
    servers = model_servers_from_ps(PS_OUTPUT)

    assert [(s["server"], s["pid"]) for s in servers] == [
        ("Ollama", 101),
        ("LM Studio", 303),
        ("ComfyUI", 404),
    ]
    assert servers[0]["rss_bytes"] == 204800 * 1024
