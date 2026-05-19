# PTIA Mobile Dashboard

Objetivo: usar o dashboard inteiro no telemovel, do Radar ate Scheduled, sem expor o painel publicamente.

## Recomendacao beta

Usar Tailscale entre o PC e o telemovel.

Porquê:
- permite abrir o dashboard fora de casa, desde que o PC esteja ligado;
- nao expoe o painel diretamente na internet;
- funciona com o backend local atual, ficheiros locais, Gemini e Buffer;
- evita construir ja uma app cloud com base de dados e login.

## Setup

1. Instala Tailscale no Windows.
2. Instala Tailscale no iPhone/Android.
3. Faz login com a mesma conta nos dois dispositivos.
4. No Windows, abre o dashboard a escutar na rede:

```powershell
cd C:\Users\joaon\ptia-content-engine
.\scripts\start_ptia_mobile_dashboard.ps1
```

5. No telemovel, abre a app Tailscale e copia o IP Tailscale do PC.
6. No browser do telemovel, abre:

```text
http://TAILSCALE_IP_DO_PC:8765
```

7. Adiciona a pagina ao ecra principal do telemovel.

## Arranque automatico

Foi criado um ficheiro no Startup do Windows:

```text
C:\Users\joaon\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\PTIA Dashboard Mobile.cmd
```

Quando fizeres login no Windows, o dashboard tenta arrancar automaticamente.
Se quiseres desativar, apaga esse ficheiro.

## Power settings

Para o dashboard continuar disponivel com o ecra desligado, o PC nao pode suspender.

Executa uma vez:

```powershell
cd C:\Users\joaon\ptia-content-engine
.\scripts\setup_mobile_power.ps1
```

Isto:
- desliga o ecra apos 10 minutos quando ligado a corrente;
- impede suspensao quando ligado a corrente;
- desativa hibernacao.

Nao muda a regra de bateria.

## Uso diario

O telemovel passa a conseguir fazer o fluxo completo:

1. Radar: colar links, pensamentos ou correr scouts.
2. Verifying: mandar verificar fontes.
3. Verified Selection: escolher 3-4 temas.
4. A Rever: validar LinkedIn, Instagram, Site e imagens.
5. Final OK: escolher horas.
6. Scheduled: enviar para Buffer ou marcar como scheduled.
7. Published: registar URL e metricas.
8. Newsletter: gerar top 5 semanal por engagement.

## Limites

- O PC tem de estar ligado e o dashboard a correr.
- Se o Windows Firewall bloquear a porta 8765, permitir acesso em rede privada/Tailscale.
- Isto e uma solucao beta. A versao final deve ter backend cloud com login, base de dados e auditoria.

## Versao cloud futura

Quando fizer sentido, migrar para:

- frontend/admin em `ptia.pt/admin`;
- autenticação;
- base de dados cloud;
- jobs agendados;
- storage de imagens;
- API para Buffer/MailerLite.

Essa versao permite trabalhar mesmo com o PC desligado, mas aumenta complexidade operacional.
