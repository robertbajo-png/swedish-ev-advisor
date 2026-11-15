# Köpsignaler i Elbilsagenten

## Första leveransen

Stabilisera publiceringskedjan före bredare källurval. Den vanliga
stagingvägen måste kunna skriva källor, kluster, artikel och
granskningsrader i en tom databas som verkställer nyckelrelationerna.
En identisk omkörning ska inte skapa dubbletter. En utebliven worker-rapport får
inte skriva över eller förväxlas med det ursprungliga felet. Detta är lokalt
syntetiskt bevis, inte bevis på verklig publicering.

Ändringen av skriptet påverkar publicerarens kodhash. Bevara kravet på exakt
giltig, självständigt granskad produktionsbevisning. Relabelera, återpublicera
eller omgranska inte äldre bevis automatiskt. Verklig driftsättning och eventuella
betalda anrop är separata beslut.

## Nästa leverans: Nytt för svenska köpare

Utgå från befintliga, publicerade artiklar och de verifierade biluppgifterna,
inte en ny datainsamling eller extra AI-anrop:

- Börja med **svenskt pris**. Välj ett exakt kanoniskt svenskt utförande och
  en redan redaktionellt granskad prisnotis vars källa uttryckligen styrker
  priset för det utförandet. Lista prisetikett, verifieringsdatum, källänk
  och en länk till det exakta utförandet. Märk kampanjpris separat; dölj
  utgångna erbjudanden. Påstå inte att priset har ändrats utan två verifierade,
  daterade värden för samma utförande och prisslag.
- Lägg till **orderstart** och **utrustningsändring** först när en officiell
  svensk källa och det granskade underlaget uttryckligen binder själva
  händelsen till rätt utförande och marknad. En allmän modellartikel, registrering
  eller en utländsk lansering räcker inte.
- Rendera korten först när de har ett explicit typfält, källreferens och exakt
  kanoniskt id. Nuvarande publika nyhetsexport har kategori, källor och
  relaterade modeller, men ingen granskad köpsignaltyp per utförande.
  Härled därför inte signaler ur rubriker, varumärken eller löptext i klienten.
  Nyhetsartiklarnas befintliga länkar till relaterade bilar ska fungera som innan.
- Testa att okänd version, preliminära uppgifter, saknad källa, fel marknad,
  utgånget erbjudande och ej publicerad artikel aldrig visas som köpsignal.
  Visa inget tomt block när noll signaler kvalificerar sig. Följ klick till
  bilsidan, inte bara antal producerade nyheter.

Det separata läsfiltret **Svenska prisnyheter** sorterar redan publicerade
prisartiklar utifrån en uttrycklig svensk prisrubrik. Det är inte en
versionsbunden köpsignal, aktuellt pris eller bevis på en prisförändring.
