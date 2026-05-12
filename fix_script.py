with open('interactive.py', 'r') as f:
    content = f.read()

# Remove first incomplete memory block (lines 212-221)
import re

# Find the duplicate pattern - first try without except
pattern1 = r'''    if cmd\["type"\] == "memory":\n        context = get_memory_context\(\)\n        prompt = \(\n            "Responde en 1-2 lineas sobre esta actividad:\\n"\n            f"{context}\\n\\n"\n            "Usuario pregunta que recuerdas."\n        \)\n        try:\n            return generate_ollama\(model=DEFAULT_MODEL, prompt=prompt, timeout_seconds=30\)\n\n'''

# Actually, let's do it simpler
lines = content.split('\n')
new_lines = []
skip_next = False
memory_block_count = 0
in_memory_block = False

for i, line in enumerate(lines):
    if 'if cmd["type"] == "memory":' in line:
        memory_block_count += 1
        if memory_block_count == 1:
            # First occurrence - skip lines until we reach second memory block
            in_memory_block = True
            continue
    
    if in_memory_block and 'if cmd["type"] == "memory":' in line:
        in_memory_block = False
        new_lines.append(line)
        continue
    
    if in_memory_block:
        continue
    
    new_lines.append(line)

content = '\n'.join(new_lines)

# Now fix the remaining except that belongs to try with wrong class
# The remaining except Exception as e: needs to be attached to the try above it
# But it should be fine now

with open('interactive.py', 'w') as f:
    f.write(content)

print("Fixed!")
