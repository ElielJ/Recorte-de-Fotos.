@echo off
rem Abre o Recorte de Fotos. Na primeira vez (ou se algo estiver faltando),
rem instala o Python e as bibliotecas necessárias automaticamente.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Recorte de Fotos
set "VENV=%~dp0.venv"
set "PY_VENV=%VENV%\Scripts\python.exe"
set "MARCA=%VENV%\requisitos_instalados.txt"

rem 1) Ambiente já pronto e com as bibliotecas atuais? Então só abre.
set "VENV_OK="
if exist "%PY_VENV%" "%PY_VENV%" -c "pass" >nul 2>&1 && set "VENV_OK=1"
if defined VENV_OK fc /b requirements.txt "%MARCA%" >nul 2>&1 && goto :abrir

echo ============================================================
echo  Preparando o Recorte de Fotos (só na primeira vez).
echo  Isso pode levar alguns minutos e precisa de internet.
echo ============================================================
echo.
if defined VENV_OK goto :instalar_bibliotecas

rem 2) Procura um Python 3.11 ou mais novo; se não houver, instala o 3.12.
call :achar_python
if not defined PYTHON (
    echo Python não encontrado. Instalando o Python 3.12...
    where winget >nul 2>&1 || goto :sem_winget
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    call :achar_python
)
if not defined PYTHON goto :python_nao_encontrado
echo Usando o Python em: %PYTHON%

rem 3) Cria o ambiente do programa (um ambiente quebrado é recriado).
if exist "%VENV%" rmdir /s /q "%VENV%"
"%PYTHON%" -m venv "%VENV%" || goto :falha

:instalar_bibliotecas
echo.
echo Instalando as bibliotecas...
"%PY_VENV%" -m pip install --upgrade pip --disable-pip-version-check -q
"%PY_VENV%" -m pip install -r requirements.txt --disable-pip-version-check || goto :falha
copy /y requirements.txt "%MARCA%" >nul
echo.
echo Pronto! Abrindo o programa...

:abrir
start "" "%VENV%\Scripts\pythonw.exe" main.py
exit /b 0

:achar_python
set "PYTHON="
call :testar_python py -3.12
call :testar_python py -3
call :testar_python python
call :testar_python "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
exit /b

:testar_python
if defined PYTHON exit /b
for /f "delims=" %%P in ('call %* -c "import sys; assert sys.version_info >= (3, 11); print(sys.executable)" 2^>nul') do set "PYTHON=%%P"
exit /b

:sem_winget
echo.
echo Não foi possível instalar o Python automaticamente (winget indisponível).
echo Instale o Python 3.12 pelo site https://www.python.org/downloads/
echo marcando a opção "Add python.exe to PATH", e abra este arquivo novamente.
pause
exit /b 1

:python_nao_encontrado
echo.
echo O Python não foi encontrado após a instalação.
echo Feche esta janela e abra este arquivo novamente.
pause
exit /b 1

:falha
echo.
echo Ocorreu um erro na instalação. Verifique a conexão com a internet e tente novamente.
pause
exit /b 1
