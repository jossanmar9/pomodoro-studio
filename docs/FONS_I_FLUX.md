# Fons de qualitat: FLUX.1 schnell i la Biblioteca de fons

## 1. Instal·lar FLUX.1 schnell en Forge

FLUX.1 [schnell] fa imatges molt millors que SDXL base i té **llicència Apache 2.0**, que en permet l'ús comercial. Necessita només 4 passos, així que és ràpid.

1. Actualitza Forge des de la seua carpeta:

   ```bash
   cd ~/IA/stable-diffusion-webui-forge
   git pull
   ```

2. Baixa el model tot en un (porta dins els codificadors de text i el VAE; pesa uns 17 GB):

   <https://huggingface.co/Comfy-Org/flux1-schnell/resolve/main/flux1-schnell-fp8.safetensors>

3. Mou-lo a la carpeta de models de Forge:

   ```bash
   mv ~/Baixades/flux1-schnell-fp8.safetensors ~/IA/stable-diffusion-webui-forge/models/Stable-diffusion/
   ```

4. Arranca Forge com sempre i, dalt de tot, tria **flux** en la interfície i `flux1-schnell-fp8` en **Checkpoint**. La primera càrrega tarda una estona.

Amb una RTX 3060 de 12 GB i 32 GB de RAM funciona; Forge mou part del model a la RAM quan cal.

Pomodoro Studio detecta el model carregat i hi adapta la configuració sola:

| Model | Passos | CFG | Mostrejador | Prompt negatiu |
|---|---:|---:|---|---|
| FLUX.1 schnell | 4 | 1 | Euler · Simple | No |
| FLUX.1 dev | 20 | 1 (destil·lat 3,5) | Euler · Simple | No |
| SDXL | 30 | 5,5 | DPM++ 2M · Karras | Sí |

L'ampliació final usa **R-ESRGAN 4x+** amb poc retoc, que dona imatges més nítides que l'antic «Latent». Si mai vols forçar un perfil, posa en `.env` `IMAGE_MODEL_PROFILE=flux-schnell` (o `sdxl`).

> **FLUX.1 dev** té una llicència no comercial. Per al canal, usa **schnell**.

## 2. Biblioteca de fons

Obri **Biblioteca de fons** des de la pàgina principal (`/fons`).

- **Generar opcions:** tria tema, llum i oratge, estil i quantes (2, 4 o 6). Es generen en segon pla i apareixen en **Per revisar**.
- **Guardar o Descartar:** només els que guardes passen a la biblioteca (`assets/backgrounds/`), amb el prompt i el model apuntats en un `.json` al costat.
- **Importar una imatge lliure:** de Pexels, Unsplash, Pixabay o pintures de domini públic. Ha de ser horitzontal i de com a mínim 1920×1080. Cal indicar la llicència i l'enllaç d'origen, que també es guarden.
- **Fons guardats:** per tema, amb l'opció d'eliminar-ne.

El **mode automàtic** tria sempre un fons guardat del tema i evita repetir els dels últims vídeos. Només en genera un de nou amb Forge si no n'hi ha cap de guardat o si marques **Generar un fons nou amb Forge (sense revisar)**.
