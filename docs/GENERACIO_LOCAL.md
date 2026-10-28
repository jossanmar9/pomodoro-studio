# Generació local: abast actual i opcions futures

Equip de referència: Linux Mint 22.3, RTX 3060 de 12 GB i uns 32 GB de RAM. És viable explorar generació local d’imatge, clips curts, efectes i música, però són ferramentes i models separats. La disponibilitat d’una GPU no assegura qualsevol resolució, duració o temps d’execució.

## Què està connectat a Pomodoro

| Recurs | Estat en Pomodoro v0.8 | Flux |
|---|---|---|
| Imatges | Connector A1111/Forge implementat | Generar → previsualitzar → acceptar → guardar procedència |
| Vídeos curts | Importació de vídeos ja creats | Copiar el clip a `assets/backgrounds/` |
| Sons ambientals | Importació i mescla; sense generador integrat | Copiar l’àudio a `assets/ambience/` |
| Música | Importació d’una pista per vídeo; sense generador integrat | Copiar l’àudio a `assets/music/` |

En el muntatge documentat, Forge ha arrancat amb detecció CUDA. No s’ha registrat encara la confirmació de l’usuari d’una primera generació acceptada des de Pomodoro. La CI prova el connector amb respostes simulades; no executa estos models en GPU.

## Ferramentes que es poden provar a banda

- **Imatges:** [Forge](https://github.com/lllyasviel/stable-diffusion-webui-forge) amb [SDXL base](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0). És la ruta ja preparada; seguix la [guia Mint](INSTAL_LINUX_MINT.md).
- **Clips curts:** [Wan 2.2 5B en ComfyUI](https://docs.comfy.org/tutorials/video/wan/wan2_2). La documentació de ComfyUI indica que el 5B pot funcionar amb 8 GB de VRAM traslladant parts del model a la RAM. Això fa raonable provar-lo amb 12 GB, però no és una mesura de rendiment de la RTX 3060. No confongues este flux amb el llançador Python original de Wan, que publica requisits diferents. Comença amb un clip curt, càmera fixa i moviment subtil.
- **Sons ambientals:** [Stable Audio Open 1.0](https://huggingface.co/stabilityai/stable-audio-open-1.0), per generar fragments estèreo de fins a 47 segons. Encara s’ha de provar en este equip. La llicència del model i les condicions d’ús comercial s’han de revisar abans d’utilitzar-lo en el canal.
- **Música:** [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5), que publica suport per a peces de fins a 10 minuts. Per a esta GPU, començaria amb **2B Turbo**, no XL: la taula del projecte recomana la família 2B per a 8–16 GB. Els temps publicats en altres GPU no són estimacions per a la RTX 3060. Tampoc està instal·lat ni verificat en este muntatge.

Les condicions de cada model, pesos i recursos de referència es revisen separadament. La llicència del codi d’una ferramenta no substituïx automàticament les condicions dels models o dels continguts que carregues.

## Muntatge d’un vídeo de diverses hores

1. Genera una imatge o un clip curt amb composició estable.
2. Revisa i prepara el bucle visual; poden fer falta edició i transicions.
3. Genera o selecciona capes de foc, pluja, vent o natura.
4. Genera o selecciona una peça instrumental; si vols diverses peces consecutives, prepara una mescla fora de Pomodoro, perquè ara no té llistes musicals automàtiques.
5. Importa els recursos, registra’n la procedència i renderitza la duració final amb FFmpeg.

No es genera tot el vídeo llarg amb difusió. Es creen recursos curts que després es repetixen i mesclen. Executa un generador cada vegada per alliberar VRAM; si també renderitzes amb NVENC, comprova la memòria disponible. Els bucles sense costura i la coherència de diverses hores requerixen revisió, no estan garantits pels generadors.
