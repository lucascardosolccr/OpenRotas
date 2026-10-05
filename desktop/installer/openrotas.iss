; ============================================================================
;  OpenRotas Desktop — Instalador (Inno Setup 6)
;  Empacota a pasta ONEDIR gerada pelo PyInstaller num instalador profissional
;  "OpenRotas Setup.exe": atalhos, diretório de dados do usuário, desinstalador,
;  e teste de integridade pós-instalação.
;
;  Pré-requisito: ter rodado  pyinstaller packaging\launcher.spec  (gera build\dist\OpenRotas\).
;  Compilar:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\openrotas.iss
;  (ou abra este .iss no Inno Setup e clique em Compile)
; ============================================================================

#define AppName "OpenRotas"
; A versão vem de desktop_config.APP_VERSION (fonte única — §19/§38), passada por
;   ISCC /DAppVersion=<x>  (build.ps1 e o workflow fazem isso). Fallback se não vier.
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppPublisher "Lucas Cruz"
#define AppExe "OpenRotas.exe"

[Setup]
AppId={{B7E2B6B0-0C3E-4E7A-9E5E-0PENROTAS0001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Dados do usuário (cache/config/logs) ficam FORA da pasta de instalação — ver §19/§31.
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=OpenRotas Setup
OutputDir=dist_installer
PrivilegesRequired=lowest
; Ícone do instalador (§38) — gerado por make_icon.py no build; usado só se existir.
#if FileExists(AddBackslash(SourcePath) + "openrotas.ico")
SetupIconFile=openrotas.ico
#endif

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
; A pasta onedir inteira do PyInstaller (app + runtime Python + libs + bases embarcadas).
; Caminho relativo à pasta deste .iss (desktop\installer\) → sobe um nível até desktop\build\...
Source: "..\build\dist\OpenRotas\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Exemplo de configuração (o app cria o real em %LOCALAPPDATA% no 1º uso).
Source: "..\config\desktop.example.json"; DestDir: "{app}\config"; Flags: ignoreversion
; [WEBVIEW2] Bootstrapper "Evergreen" do Microsoft Edge WebView2 Runtime — o motor que a janela
; nativa (pywebview) usa para desenhar o app. O workflow de build baixa este .exe para a pasta
; do instalador; se não estiver presente no momento da compilação, o bloco é ignorado (instalador
; compila mesmo assim). Vai para {tmp} e é removido após a instalação.
#if FileExists(AddBackslash(SourcePath) + "MicrosoftEdgeWebview2Setup.exe")
  #define HasWebView2Setup
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: WebView2Faltando
#endif

[Dirs]
; Diretório PERSISTENTE de dados do usuário (sobrevive a updates/desinstalação controlada).
Name: "{localappdata}\{#AppName}"; Flags: uninsneveruninstall
Name: "{localappdata}\{#AppName}\cache"; Flags: uninsneveruninstall
Name: "{localappdata}\{#AppName}\config"; Flags: uninsneveruninstall
Name: "{localappdata}\{#AppName}\logs"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Central de Dados (baixar o Brasil inteiro)"; Filename: "{app}\{#AppExe}"; Parameters: "--central"
Name: "{group}\Diagnóstico do OpenRotas"; Filename: "{app}\{#AppExe}"; Parameters: "--diagnostico"
Name: "{group}\Saúde dos Dados Nacionais"; Filename: "{app}\{#AppExe}"; Parameters: "--saude-nacional --html"
Name: "{group}\Auditoria de Cobertura Nacional"; Filename: "{app}\{#AppExe}"; Parameters: "--auditoria --relatorio"
Name: "{group}\Catálogo de Dados Nacionais"; Filename: "{app}\{#AppExe}"; Parameters: "--fontes --md"
Name: "{group}\Mapa de Cobertura Nacional"; Filename: "{app}\{#AppExe}"; Parameters: "--mapa-cobertura"
Name: "{group}\Auditoria de Integridade"; Filename: "{app}\{#AppExe}"; Parameters: "--integridade"
Name: "{group}\Conectividade da Malha"; Filename: "{app}\{#AppExe}"; Parameters: "--conectividade"
Name: "{group}\Telemetria (atualizar)"; Filename: "{app}\{#AppExe}"; Parameters: "--telemetria-ana --atualizar"
Name: "{group}\Central de Recursos"; Filename: "{app}\{#AppExe}"; Parameters: "--recursos --html"
Name: "{group}\Verificar atualizações"; Filename: "{app}\{#AppExe}"; Parameters: "--atualizar"
Name: "{group}\Reparar instalação"; Filename: "{app}\{#AppExe}"; Parameters: "--reparar"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; [WEBVIEW2] Garante o runtime do WebView2 ANTES de validar/abrir o app — sem ele a janela
; nativa não desenha. Roda silencioso e só se o runtime estiver faltando. Não é fatal: se a
; instalação do runtime falhar (ex.: sem internet), o app ainda abre no navegador como alternativa.
#ifdef HasWebView2Setup
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Instalando o componente de exibição (Microsoft WebView2)..."; Flags: waituntilterminated; Check: WebView2Faltando
#endif
; Teste de integridade pós-instalação (§18/§30): roda o diagnóstico silencioso; se falhar,
; o usuário é avisado mas a instalação não é abortada (ele pode reparar depois).
Filename: "{app}\{#AppExe}"; Parameters: "--diagnostico --silencioso"; StatusMsg: "Validando a instalação..."; Flags: runhidden; Check: SempreExecutar
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName} agora"; Flags: nowait postinstall skipifsilent

[Code]
function SempreExecutar: Boolean;
begin
  Result := True;
end;

{ Detecta se o Microsoft Edge WebView2 Runtime (Evergreen) JÁ está instalado na máquina,
  consultando a chave 'pv' do cliente de atualização do runtime (GUID oficial do WebView2),
  tanto por máquina (HKLM, 32/64 bits) quanto por usuário (HKCU). Devolve True quando o
  runtime está AUSENTE (ou seja, precisa instalar). }
function WebView2Faltando: Boolean;
var
  pv: string;
  Guid: string;
begin
  Guid := '{{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}}';
  pv := '';
  if not RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + Guid, 'pv', pv) then
    if not RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + Guid, 'pv', pv) then
      RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + Guid, 'pv', pv);
  Result := (pv = '') or (pv = '0.0.0.0');
end;
