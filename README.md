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
- roda uma vez por dia às 2:00
- se o Mac estiver dormindo no horário, o macOS executa o agendamento quando ele voltar a ficar ativo
- cria automaticamente a pasta de destino e `backup_outlook.log` se ainda não existirem

## Caminho do Outlook e destino

Origem padrão:

```bash
auto
```

Com `ORIGEM="auto"`, o programa tenta localizar o perfil real do Outlook no macOS. Ele testa caminhos conhecidos, como `Outlook Profiles/Main Profile`, `Outlook 15 Profiles/Main Profile` e `Outlook 15 Profiles/Main Identity`, e também procura por nomes de perfil conhecidos em pastas prováveis da Library.

Destino padrão:

```bash
$HOME/Library/CloudStorage/OneDrive/Outlook-Backups
```

## Instalação inicial

Clone o projeto a partir da pasta pai. Não execute `git clone` estando dentro de outra pasta `backup-outlook`, pois isso criará uma cópia aninhada.

```bash
cd "$HOME"
git clone https://github.com/rrfj10/backup-outlook.git backup-outlook
cd "$HOME/backup-outlook"
```

Crie a configuração privada. O arquivo `.env` não deve ser publicado no GitHub:

```bash
mkdir -p "$HOME/Library/Application Support/BackupOutlook"
cp .env.example "$HOME/Library/Application Support/BackupOutlook/.env"
chmod 600 "$HOME/Library/Application Support/BackupOutlook/.env"
```

Edite `DESTINO` se quiser mudar a pasta de backup. Mantenha `ORIGEM="auto"` para detectar o perfil do Outlook automaticamente, ou informe um caminho manual se tiver um perfil específico:

```bash
nano "$HOME/Library/Application Support/BackupOutlook/.env"
```

Instale a automação:

```bash
chmod +x install_automation.sh
./install_automation.sh
```

O instalador copia o script para `~/Library/Application Support/BackupOutlook` e instala o agente diário às 2:00. O projeto clonado é apenas a fonte de atualização; o macOS executa a cópia de produção.

Na primeira execução, o programa cria automaticamente o destino configurado e o arquivo `backup_outlook.log`. Não é necessário criar o log manualmente.

Verifique a instalação:

```bash
launchctl list | grep -E 'backupoutlook|backup.outlook'
```

O resultado esperado é:

```text
-       0       com.backupoutlook.daily
```

## Atualizar a produção

Quando houver uma nova versão no GitHub, entre na pasta do clone existente e atualize-a. Não execute `git clone` novamente:

```bash
cd "$HOME/backup-outlook"
git pull origin main
./install_automation.sh
```

O instalador atualiza a cópia de produção, preserva o `.env` existente e recarrega o agente diário.

## Operação manual

Feche completamente o Outlook antes de executar backup ou restauração.

### Fazer backup

```bash
python3 "$HOME/Library/Application Support/BackupOutlook/backup_outlook_professional.py" backup
```

Para forçar uma nova cópia mesmo sem alterações detectadas:

```bash
python3 "$HOME/Library/Application Support/BackupOutlook/backup_outlook_professional.py" backup --force
```

### Ver backups disponíveis

```bash
python3 "$HOME/Library/Application Support/BackupOutlook/backup_outlook_professional.py" list
```

### Ver o último backup

```bash
python3 "$HOME/Library/Application Support/BackupOutlook/backup_outlook_professional.py" latest
```

### Restaurar o último backup

```bash
python3 "$HOME/Library/Application Support/BackupOutlook/backup_outlook_professional.py" restore-latest
```

### Restaurar um backup específico

```bash
python3 "$HOME/Library/Application Support/BackupOutlook/backup_outlook_professional.py" restore "$HOME/Library/CloudStorage/OneDrive/Outlook-Backups/Outlook_Profile_YYYYMMDD_HHMMSS.zip"
```

### Limpar backups antigos

```bash
python3 "$HOME/Library/Application Support/BackupOutlook/backup_outlook_professional.py" cleanup --days 30 --count 20
```

## Agendamento no macOS

O agente diário fica em:

```bash
~/Library/LaunchAgents/com.backupoutlook.daily.plist
```

Se o Mac estiver dormindo às 2:00, o macOS executa o agendamento quando voltar a ficar ativo.

Para remover o agente:

```bash
launchctl bootout "gui/$(id -u)/com.backupoutlook.daily"
```

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
- cada execução também grava eventos em `backup_outlook.log` dentro do destino configurado
- para recuperar uma pasta específica, idealmente restaure o perfil completo e depois acesse a estrutura original

## Configuração por ambiente

Copie o modelo para a configuração local da automação:

```bash
cp .env.example "$HOME/Library/Application Support/BackupOutlook/.env"
```

Edite esse arquivo e altere `DESTINO` conforme necessário. Mantenha `ORIGEM="auto"` para detectar o perfil do Outlook automaticamente, ou substitua por um caminho manual se precisar apontar para um perfil específico. O arquivo `.env` real é ignorado pelo Git e não será publicado. Variáveis definidas diretamente no shell têm prioridade sobre o `.env`. Se o arquivo existir, mas não puder ser lido, o programa interromperá a execução em vez de usar um destino diferente silenciosamente.

Exemplo de configuração:

```bash
ORIGEM="auto"
DESTINO="$HOME/Library/CloudStorage/OneDrive/Outlook-Backups"
```

## Quando usar

Use o backup manual antes de:
- trocar conta de e-mail
- reinstalar o Outlook
- mudar de computador
- migrar dados do sistema
