# REMOTE-LINUX Android

Aplicativo Android inicial para abrir a área de trabalho Linux hospedada no Railway através do noVNC.

## Gerar APK
O GitHub Actions compila automaticamente a cada push na branch main. Acesse Actions > Build Android APK e baixe o artefato REMOTE-LINUX-APK.

## Observação
O app abre o desktop remoto configurado em MainActivity.kt. O serviço Railway precisa estar online e com VNC_PASSWORD configurada para que a tela noVNC consiga autenticar.
