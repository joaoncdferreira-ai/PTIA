import json
from pathlib import Path

def polish_posts():
    filepath = Path('data/final_posts.jsonl')
    temp_filepath = filepath.with_suffix('.tmp')
    
    updates = {
        'post_3fc3d7e49759324e63': {
            'body': "O Canadá acaba de lançar o programa 'AI for All', a sua nova estratégia nacional de IA. Liderada por Mark Carney, a iniciativa mostra como a união entre visão política e mercados financeiros pode acelerar a produtividade económica. Lições de competitividade real. 🇨🇦"
        },
        'post_b1be62faeb38e227df': {
            'body': "Lisboa vai acolher os Health AI Innovation Awards em 2026. A escolha reflete a crescente maturidade do ecossistema de saúde e tecnologia em Portugal. O desafio agora é converter a visibilidade em investimento real e captação de talento. 🇵🇹🏥 #HealthAI"
        },
        'post_81cca8665b434bdec2': {
            'title': "IBM e Google Cloud expandem parceria estratégica para escalar IA corporativa",
            'body': "IBM e Google Cloud reforçam aliança estratégica para escalar IA generativa no segmento enterprise. A Google foca-se na integração dos seus modelos em fluxos de trabalho e plataformas corporativas já existentes. A batalha da IA ganha-se no hábito e na usabilidade. ☁️🤖"
        },
        'post_3383a7e8b953fb8cc3': {
            'title': "IBM e Google Cloud: Parceria Estratégica para Escalar IA no Segmento Enterprise",
            'body': "A IBM e a Google Cloud anunciaram hoje uma expansão da sua parceria estratégica para ajudar as empresas a adotar e escalar soluções de inteligência artificial generativa. A aliança combina a experiência de entrega da IBM Consulting com a tecnologia de IA da Google Cloud para criar valor prático e integrar capacidades analíticas no dia a dia organizacional.\n\nA verdadeira leitura crítica deste movimento está na distribuição e na fricção de adoção. Ao focar-se na otimização de fluxos de trabalho existentes, a Google Cloud reconhece que a liderança da IA não dependerá apenas da superioridade teórica de modelos proprietários, mas sim de se tornar a camada padrão incorporada nos produtos de produtividade e pesquisa que milhões de utilizadores já dominam. É a captura do hábito como barreira competitiva de entrada.\n\nPara os líderes de tecnologia e inovação em Portugal, a lição é clara: a produtividade real não virá de ferramentas isoladas ou roadmaps avulsos, mas da simbiose com plataformas operacionais preexistentes. Acelerar a adoção organizacional significa reduzir a fricção e alavancar infraestruturas já enraizadas."
        }
    }
    
    print(f"Polishing posts in {filepath}...")
    updated_count = 0
    
    with open(filepath, 'r', encoding='utf-8') as infile, open(temp_filepath, 'w', encoding='utf-8') as outfile:
        for line in infile:
            if not line.strip():
                continue
            post = json.loads(line)
            post_id = post.get('post_id') or post.get('id')
            if post_id in updates:
                for key, val in updates[post_id].items():
                    post[key] = val
                print(f"  Updated post: {post_id} ({post.get('channel')})")
                updated_count += 1
            outfile.write(json.dumps(post, ensure_ascii=False) + '\n')
            
    if updated_count > 0:
        import os
        os.replace(str(temp_filepath), str(filepath))
        print(f"Successfully polished {updated_count} posts!")
    else:
        if temp_filepath.exists():
            temp_filepath.unlink()
        print("No posts were updated.")

if __name__ == '__main__':
    polish_posts()
