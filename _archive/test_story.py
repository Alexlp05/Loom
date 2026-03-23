import sys
sys.path.append('.')
from TextToStory.story_generator_local import generate_story_local

transcript_path = r'outputs\transcript_20260306-115343.txt'
with open(transcript_path, encoding='utf-8') as f:
    transcript = f.read()

print("--- STARTING GENERATION ---", flush=True)
story = generate_story_local(transcript)
print("\n--- STORY ---", flush=True)
print(story)
print("--- END ---", flush=True)
