import json

def view():
    filepath = 'data/final_posts.jsonl'
    with open(filepath, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f, 1):
            if not line.strip():
                continue
            post = json.loads(line)
            if post.get('topic_id') == 'topic_59a3ffda3f2e96e403':
                print("="*40)
                print(f"Index: {idx} | Channel: {post.get('channel')}")
                print(f"Title: {post.get('title') or post.get('post_title')}")
                print(f"Body: {post.get('body')}")

if __name__ == '__main__':
    view()
