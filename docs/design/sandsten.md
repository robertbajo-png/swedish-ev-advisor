# Sandsten: Elbilsagentens startsida

## Designbeslut
- B Sandsten: varm pappersyta `#f8f4ed`, mörk brun text `#332820`, terrakotta `#863c29` och mjukt sandfält `#eee2d4`. Newsreader för de större redaktionella rubrikerna, Manrope för kontroller och löptext. Typsnitten serveras lokalt.
- Lugn öppning med tydlig huvudrubrik, AI-frågerutan först och en sammanhängande landskapsbild efter rådgivaren. Separata, luftiga områden för Din körvecka, nyheter och bilurvalet. Bildkrediter i sidfoten; materialvillkor stannar vid berörd uppgift.
- Mest räckvidd för pengarna flyttar fokus till Din körvecka; huvudmenyn erbjuder en separat ingång. Knappen vid körveckan kan förbereda en fråga men får inte skicka den automatiskt. Körsträckan och laddmixen behålls vid bilurval och kalkyl.
- Endast startsidan omfattas. Katalog, artiklar, rättigheter för befintliga bilbilder, rådgivarens API och kalkylens affärsregler ändras inte.
- Designgrunden är den fastnålade OpenAI Frontend Design Skill på `82d2c5b44ac234ec0f204f647562a4349d90ef43`. Ägaren valde B och bad 27 november 2026 att publicera den nya designen. En senare större designändring ska granskas här och godkännas separat.

## Kontroller innan publicering
- Faktisk förstasida på 320, 390, 768, 1024 och 1440 px: inga avklippta rubriker/överflöden; rådgivare, bild, navigering och kontroller är läsbara.
- Testa tangentbordsfokus, båda körveckeingångarna, redigering efter bilurval samt att vald distans och laddmix når kostnaden. Testa rådgivartransport isolerat utan betalda anrop.
- Katalog-, SEO- och produktionskontroller gäller oförändrat. Vid blockerad prisverifiering: behåll föregående produktionsversion. Publicera enbart via den befintliga kontrollerade vägen och verifiera den verkliga aktivt levererade sidan efteråt.
