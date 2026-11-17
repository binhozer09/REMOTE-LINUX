# REMOTE-LINUX

Ambiente Linux gráfico remoto hospedado no Railway, acessível pelo navegador e futuramente pelo aplicativo Android.

## Componentes

- Ubuntu 24.04
- XFCE Desktop
- Xvfb (display virtual)
- x11vnc (servidor VNC limitado a localhost)
- noVNC + websockify (acesso via navegador/WebSocket)

## Implantação no Railway

1. Crie um serviço no projeto Railway e conecte este repositório.
2. O Railway detecta o `Dockerfile` e constrói a imagem.
3. Em **Variables**, configure `VNC_PASSWORD` com uma senha forte de pelo menos 8 caracteres.
4. Configure o domínio público do serviço. A aplicação escuta em `PORT` (padrão 8080).
5. Abra `https://SEU-DOMINIO/vnc.html?autoconnect=true&resize=remote&path=websockify`.

O Railway fornece HTTPS/WSS no domínio público. O VNC fica vinculado somente a localhost; não exponha a porta 5900.

## Variáveis

| Nome | Obrigatória | Descrição |
|---|---|---|
| `VNC_PASSWORD` | Sim | Senha VNC; configure somente no Railway, nunca no Git |
| `SCREEN_SIZE` | Não | Resolução, padrão `1280x800x24` |
| `PORT` | Fornecida pelo Railway | Porta HTTP no Railway, padrão local 8080 |

## Segurança e limitações

- Use uma senha exclusiva e forte.
- O acesso público deve ficar protegido; a senha VNC é solicitada ao conectar.
- Este primeiro estágio entrega um desktop remoto funcional. O APK Android, login próprio e controles adicionais serão desenvolvidos em etapas separadas.
- Sessões e processos podem ser reiniciados quando o Railway reinicia ou substitui a instância. Para persistência de arquivos, será necessário configurar um Volume Railway.

