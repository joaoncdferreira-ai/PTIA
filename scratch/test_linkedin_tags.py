import sys
import json
import time
from pathlib import Path

# Add src to PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ptia_engine.dashboard import _final_post_text

class MockPost:
    def __init__(self, title, body, channel="linkedin", hashtags="", source_urls=None):
        self.title = title
        self.body = body
        self.channel = channel
        self.hashtags = hashtags
        self.source_urls = source_urls or []

def run_tests():
    print("=== A INICIAR TESTES DE VALIDAÇÃO E AUTO-APRENDIZAGEM ===")
    
    # 1. Testar Cenários Estáticos Padrão
    test_cases = [
        {
            "name": "Empresa Simples Mapeada (NVIDIA)",
            "body": "chips de inteligência artificial da @NVIDIA e da @AMD.",
            "expected_contains": ["NVIDIA", "AMD"]
        },
        {
            "name": "Case-Insensitivity (@nvidia)",
            "body": "A @nvidia lançou o novo chip Blackwell com a @amd.",
            "expected_contains": ["NVIDIA", "AMD"]
        },
        {
            "name": "Empresa com Espaços (@Jornal de Negócios)",
            "body": "Segundo o @Jornal de Negócios, a taxa de adoção subiu.",
            "expected_contains": ["Jornal de Negócios"]
        },
        {
            "name": "Perfil Pessoal (Limpeza Editorial)",
            "body": "O @Vasco Pedro, CEO da @Unbabel, esteve no evento com @Daniela Braga.",
            "expected_contains": ["Vasco Pedro", "Unbabel", "Daniela Braga"],
            "not_contains": ["@Vasco", "@Daniela"]
        }
    ]
    
    passed_all = True
    for idx, tc in enumerate(test_cases, 1):
        print(f"\nCaso {idx}: {tc['name']}")
        post = MockPost(title="Test Title", body=tc["body"])
        result = _final_post_text(post)
        
        passed = True
        for exp in tc["expected_contains"]:
            if exp not in result:
                print(f"  [ERRO] Não encontrou: '{exp}'")
                passed = False
                passed_all = False
        
        for not_exp in tc.get("not_contains", []):
            if not_exp in result:
                print(f"  [ERRO] Encontrou indesejado: '{not_exp}'")
                passed = False
                passed_all = False
                
        if passed:
            print("  [OK] Passou!")

    # 2. Testar o Motor de Auto-Aprendizagem (Auto-Resolver de Novas Entidades)
    print("\n--- Teste de Auto-Aprendizagem (Self-Learning Loop) ---")
    
    # Garantir que a entidade de teste não está mapeada no início
    map_path = Path("config/linkedin_urn_map.json")
    if map_path.exists():
        data = json.loads(map_path.read_text(encoding="utf-8"))
        if "fundação champalimaud" in data.get("companies", {}):
            del data["companies"]["fundação champalimaud"]
            map_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            print("  [Setup] Removida 'Fundação Champalimaud' temporariamente da base de dados.")

    # Simular post com a nova menção @Fundação Champalimaud
    test_body = "A @Fundação Champalimaud está a liderar investigação oncológica com IA em Portugal."
    print(f"  Texto de Entrada: {test_body}")
    
    post = MockPost(title="Nova Investigação", body=test_body)
    
    # Primeiro carregamento: Deve limpar o @ como fallback (texto limpo) e disparar o worker assíncrono
    result_1 = _final_post_text(post)
    print(f"  Saída 1 (Instante 0 - Fallback Seguro):  {result_1}")
    
    if "@Fundação Champalimaud" in result_1 or "Fundação Champalimaud" not in result_1:
        print("  [ERRO] Fallback de texto inicial incorreto.")
        passed_all = False
    else:
        print("  [OK] Primeiro carregamento elegante e limpo.")

    # Aguardar que o worker assíncrono conclua a pesquisa e resolução
    wait_time = 45
    print(f"  [Auto-Resolver] A aguardar {wait_time} segundos para resolução em background...")
    time.sleep(wait_time)
    
    # Verificar se a entidade foi adicionada à base de dados
    if map_path.exists():
        data = json.loads(map_path.read_text(encoding="utf-8"))
        companies = data.get("companies", {})
        if "fundação champalimaud" in companies:
            resolved_info = companies["fundação champalimaud"]
            print(f"  [Auto-Resolver] Encontrado URN adicionado: {resolved_info['urn']}")
            print("  [OK] O ficheiro de configuração foi atualizado de forma dinâmica!")
            
            # Segundo carregamento: Agora deve renderizar a tag oficial limpa!
            result_2 = _final_post_text(post)
            print(f"  Saída 2 (Instante T - Tag Resolvida):  {result_2}")
            
            expected_tag = "Fundação Champalimaud"
            if expected_tag in result_2:
                print("  [OK] Nome formatado da empresa foi aplicado com sucesso!")
            else:
                print(f"  [ERRO] Nome esperado '{expected_tag}' não foi aplicado na saída.")
                passed_all = False
        else:
            print("  [ERRO] A entidade 'Fundação Champalimaud' não foi adicionada ao mapeamento.")
            passed_all = False
            
    print("\n==============================================")
    if passed_all:
        print("[SUCESSO] TODOS OS TESTES PASSARAM COM SUCESSO!")
    else:
        print("[ERRO] ALGUNS TESTES FALHARAM. VERIFICAR LOGS.")
    print("==============================================")

if __name__ == "__main__":
    run_tests()
