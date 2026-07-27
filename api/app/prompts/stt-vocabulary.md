# STT — amorce de vocabulaire

<!--
Whisper takes a `prompt` argument, but it is NOT an instruction — it is treated
as if it were the transcript of the audio immediately preceding this clip.
Whisper does not follow orders; it continues a context. So this file must be a
*sample of the expected vocabulary*, not a list of rules. Writing "transcris
fidèlement et n'invente rien" here would do nothing useful and would risk
Whisper echoing that sentence into the transcript.

Effect: it biases decoding towards the domain terms and the code-switching
pattern, which is where a generic Whisper mangles Darija chantier reports
("gollote" for goulotte, "brasage" for brassage, French numbers inside Arabic
sentences).

Keep it under ~200 tokens: Whisper only reads the tail of this window, so a
long file silently drops its own beginning.
-->

Rapport de chantier, aznet, câblage réseau. Salam, lyoum f chantier Marina Center,
client OCP. Rakebna miya w khamsin metre dyal goulotte f couloir, w jerrina tmn miya
metre dyal câble réseau. Kmmalna khamsa dyal bureaux f l'étage l'lewel, w raccordina
juj panneaux de brassage. Prise RJ45, baie de brassage, chemin de câbles, goulotte,
gaine, fibre optique, tableau électrique, faux plafond. Kayn chi problème f
l'ascenseur, ma qdrnach ntl3o l'étage tmnya. Khass matériel ghedda : goulottes w
colliers. Chantier Anfa Place, Technopark, Casa Finance City, Zenith Millenium,
Bouskoura, Sidi Maarouf. Client Attijari, Maroc Telecom, CNSS, Renault.
