# Backup do Outlook

Este projeto salva o perfil do Outlook em snapshots no OneDrive e mantém uma rotina automática no macOS.

## Requisitos

- macOS
- Python 3.9 ou superior
- Microsoft Outlook para Mac
- OneDrive instalado e configurado, caso o destino esteja no OneDrive

O projeto usa somente a biblioteca padrão do Python. O arquivo `requirements.txt` documenta que não há pacotes externos para instalar.

Para verificar a instalação:

```bash
python3 --version
python3 -m pip install -r requirements.txt
```

O comando `pip` não instalará pacotes adicionais.

## O que ele faz

- compacta o perfil do Outlook em arquivos ZIP no destino de backup
- cria snapshots com data e hora
- mantém backups recentes automaticamente
- permite restaurar o último snapshot ou um específico
- roda todos os dias às 2:00
- roda também uma vez ao fazer login no macOS

## Caminho do Outlook e destino

Origem padrão:

```bash
$HOME/Library/Group Containers/UBF8T346G9.Office/Outlook/Outlook 15 Profiles/Main Profile
```

Destino padrão:

```bash
$HOME/Library/CloudStorage/OneDrive/Outlook-Backups
```

## Comandos principais

### Fazer backup manual

```bash
cd <diretorio-do-projeto>
python3 backup_outlook_professional.py backup
```

Para forçar uma nova cópia mesmo sem alterações detectadas:

```bash
python3 backup_outlook_professional.py backup --force
```

### Ver backups disponíveis

```bash
python3 backup_outlook_professional.py list
```

### Ver o último backup

```bash
python3 backup_outlook_professional.py latest
```

### Restaurar o último backup

```bash
python3 backup_outlook_professional.py restore-latest
```

### Restaurar um backup específico

```bash
python3 backup_outlook_professional.py restore "$HOME/Library/CloudStorage/OneDrive/Outlook-Backups/Outlook_Profile_YYYYMMDD_HHMMSS.zip"
```

### Limpar backups antigos

```bash
python3 backup_outlook_professional.py cleanup --days 30 --count 20
```

## Agendamento no macOS

### Backup diário às 2:00

Agente em:

```bash
~/Library/LaunchAgents/com.backupoutlook.daily.plist
```

### Backup ao fazer login

Agente em:

```bash
~/Library/LaunchAgents/com.backupoutlook.login.plist
```

### Verificar se os agentes estão ativos

```bash
launchctl list | grep -E 'backupoutlook|backup.outlook'
```

### Remover os agentes

```bash
launchctl bootout "gui/$(id -u)/com.backupoutlook.daily"
launchctl bootout "gui/$(id -u)/com.backupoutlook.login"
```

### Instalar a automação

Execute uma vez a partir desta pasta:

```bash
./install_automation.sh
```

O instalador mantém uma cópia operacional em `~/Library/Application Support/BackupOutlook`, instala os agentes do macOS e recarrega os serviços. Depois da instalação, o SSD externo pode ficar desconectado.

## Importante

- o backup é do perfil completo do Outlook em um arquivo ZIP
- a compactação pode consumir CPU durante o backup, mas reduz a quantidade de arquivos que o OneDrive precisa sincronizar
- cada novo ZIP precisa ser sincronizado por inteiro; para perfis que mudam muito, isso pode reduzir a vantagem da compactação
- a rotina registra uma assinatura pequena do perfil e não cria outro ZIP quando nada mudou
- quando houver alteração, o backup ainda será uma cópia completa; um perfil de 6 GB continuará exigindo uma sincronização grande
- snapshots antigos em formato de pasta continuam podendo ser listados e restaurados
- o programa sempre cria um ZIP do perfil atual antes de substituir a pasta durante uma restauração
- antes de iniciar uma operação grande, o programa verifica o espaço livre e interrompe a operação se a margem for insuficiente
- somente o último ZIP `*.pre_restore_*.zip` é mantido localmente; os anteriores são removidos após uma restauração bem-sucedida
- o programa bloqueia backup e restauração enquanto o Microsoft Outlook estiver aberto
- para recuperar uma pasta específica, idealmente restaure o perfil completo e depois acesse a estrutura original

## Configuração por ambiente

Copie o modelo para a configuração local da automação:

```bash
cp .env.example "$HOME/Library/Application Support/BackupOutlook/.env"
```

Edite esse arquivo e altere `ORIGEM` e `DESTINO` conforme necessário. O arquivo `.env` real é ignorado pelo Git e não será publicado. Variáveis definidas diretamente no shell têm prioridade sobre o `.env`.

Exemplo de configuração:

```bash
ORIGEM="$HOME/Library/Group Containers/UBF8T346G9.Office/Outlook/Outlook 15 Profiles/Main Profile"
DESTINO="$HOME/Library/CloudStorage/OneDrive/Outlook-Backups"
```

## Quando usar

Use o backup manual antes de:
- trocar conta de e-mail
- reinstalar o Outlook
- mudar de computador
- migrar dados do sistema
