export const CHAMPIONS = [
  'Aatrox','Ahri','Akali','Akshan','Alistar','Amumu','Anivia','Annie','Aphelios','Ashe',
  'AurelionSol','Azir','Bard','BelVeth','Blitzcrank','Brand','Braum','Briar','Caitlyn','Camille',
  'Cassiopeia','ChoGath','Corki','Darius','Diana','DrMundo','Draven','Ekko','Elise','Evelynn',
  'Ezreal','Fiddlesticks','Fiora','Fizz','Galio','Gangplank','Garen','Gnar','Gragas','Graves',
  'Gwen','Hecarim','Heimerdinger','Hwei','Illaoi','Irelia','Ivern','Janna','JarvanIV','Jax',
  'Jayce','Jhin','Jinx','KSante','KaiSa','Kalista','Karma','Karthus','Kassadin','Katarina',
  'Kayle','Kayn','Kennen','KhaZix','Kindred','Kled','KogMaw','LeBlanc','LeeSin','Leona',
  'Lillia','Lissandra','Lucian','Lulu','Lux','Malphite','Malzahar','Maokai','MasterYi','MissFortune',
  'Mordekaiser','Morgana','Nami','Nasus','Nautilus','Neeko','Nidalee','Nilah','Nocturne','Nunu',
  'Olaf','Orianna','Ornn','Pantheon','Poppy','Pyke','Qiyana','Quinn','Rakan','Rammus',
  'RekSai','Rell','Renata','Renekton','Rengar','Riven','Rumble','Ryze','Samira','Sejuani',
  'Senna','Seraphine','Sett','Shaco','Shen','Shyvana','Singed','Sion','Sivir','Skarner',
  'Smolder','Sona','Soraka','Swain','Sylas','Syndra','TahmKench','Taliyah','Talon','Taric',
  'Teemo','Thresh','Tristana','Trundle','Tryndamere','TwistedFate','Twitch','Udyr','Urgot','Varus',
  'Vayne','Veigar','VelKoz','Vex','Vi','Viego','Viktor','Vladimir','Volibear','Warwick',
  'Wukong','Xayah','Xerath','XinZhao','Yasuo','Yone','Yorick','Yuumi','Zac','Zed',
  'Zeri','Ziggs','Zilean','Zoe','Zyra',
];

export const ROLES = ['Top', 'Jungle', 'Mid', 'ADC', 'Support'] as const;
export type Role = typeof ROLES[number];

export const SUMMONER_SPELLS = ['Flash', 'Ignite', 'Teleport', 'Barrier', 'Exhaust', 'Cleanse', 'Ghost', 'Heal'] as const;

export const POSITIONS = ['under_tower', 'safe', 'middle', 'extended', 'river'] as const;
export const WAVE_POSITIONS = ['frozen_near_me', 'pushing_to_me', 'middle', 'slow_push_to_them', 'crashed'] as const;
export const ENEMY_JG_LOCATIONS = ['topside', 'botside', 'mid', 'unknown'] as const;
