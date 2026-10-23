"""THE SEATS AND THE SLEEVE AS TWO NUMBERS (release E5-S, Oct 11, 2026): the tests' own side of the rule, by hand.

`equity_money.probe.max_programs` (the seats) and `probe.sleeve_share` (a seat's share of E) are set together by one
mechanical step (`set_design SEATS SLEEVE`: the constitution's `probe` comment). No test of the tree may assume the
pair in force, so every expected size and count is computed HERE, from the table's rows and the rule written out in
this file, and never by calling the code under test:

- `Rows`, `rows_of`: the rows the rule reads, from a constitution (the one in force, or a candidate's: `constitution_at`).
- `walk`: the sizing rule of league/equity/sizing.py's docstring written out as arithmetic, one ask after another (the
  caps in the order ties are named, the floor to whole millionths of a share, the minimum order).
- `figures`: the closed forms the documents state (a one-ETF lot, how many lots fit under each cap, the budget's E).
  league/tests/test_equity_design.py holds each to `walk` and to the House's own `size_entry` (`Lane`).
- `Lane`: an equity lane sized by the REAL `size_entry` on the facts `EquityBook._size` states to it.
- `CANDIDATES`, `REFERENCE`, `DIGESTS`: the pre-registered study EQDONE-3's grid (seats 3, 4, 5, 6 x sleeve 0.50, 0.33,
  0.25), A20's design (three seats at 0.50: what E1 deployed, and the rollback) and each candidate's pinned digests.
- `design`, `reference`: the constitution patched to a candidate for a test's body, so a pin of A20's own figures
  (a digest, a dollar size) is read at A20's design whatever pair is in force.
- THE SEAT RULE'S BLOCK (release E5-A; `equity_money.probe.seat`) and THE PANEL ROW (release E4 step two;
  `equity_money.panel`) are rows of the table, so each moved every pair's digests once: `DIGESTS` are the pins with
  both as they stand; `DIGESTS_E5A` are release E5-A's, which each pair still has with the panel row left out
  (`without_panel`); `DIGESTS_E5S` are release E5-S's, which each pair still has with both left out
  (`without_seat`). `e1` is A20's design as release E1 deployed it (neither: E1's own digests); `seat_rule` patches
  the rule's rows. ONE OPEN STRUCTURE A PROBE FAMILY (Oct 15, 2026: `options_money.probe.open_per_family` 3 -> 1) is a
  row of the same money table, so it moved every pair's digests once more: `DIGESTS_E4S2` are the pins before it, which
  each pair still has with that row set back (`before_opf1`); every older table's helper sets it back too. THE OLD
  LANES ARE EXITS ONLY (`equity_money.enabled` True -> False: the owner's goal of Oct 19, 2026 and PREREG-EVL-1, section
  8) is a row of the table too, so it moved every pair's digests once more: `DIGESTS_OPENS_ON` are the pins before it,
  which each pair still has with that row set back (`opens_on`); every older table's helper sets it back too. RELEASE
  R2's rows (the event block, the stock share at 0.10) moved them once more (`DIGESTS_STOP` before them, `before_r2`),
  and RELEASE 1019c's row (`equity_money.event.max_orders_day`, the event kind's own day order line) once more:
  `DIGESTS_R2` are the pins before it, which each pair still has with that row left out (`before_1019c`). THE CAPTAIN'S
  A86 REVISED (the Probe band's size: `event.position_share.probe` 0.05 -> 0.035, the new `event.one_share_max.probe`
  0.05; `event.max_open.probe` STAYS 6) moved them once more: `DIGESTS_1019C` are the pins before it, which each pair still
  has with those rows set back (`before_a86`); every older table's helper sets them back too. RELEASE 1019h's rows (the
  captain's A97 S2 and A100: `event.reach_bar.probe` and `.sized`, Done's size bar a Probe or Sized buy rounds up to)
  moved them once more: `DIGESTS_A86` are the pins before them, which each pair still has with those rows left out
  (`before_1019h`); every older table's helper leaves them out too. RELEASE 1019i's row (PREREG-EVL-6 section 6, the
  captain's A99 and A100: `event.max_open_v6.probe` 14, the Probe slots of the versions registered at or after
  REGISTERED_AT_6) moved them once more: `DIGESTS_1019H` are the pins before it, which each pair still has with that row
  left out (`before_1019i`); every older table's helper leaves it out too. THE OWNER'S GOAL V3's ROWS (A138, release
  1019l) moved them once more (`DIGESTS_1019I` before them, `before_1019l`), and RELEASE 1019n's row (PREREG-EVL-8
  section 4.1, A122: `event.max_open_v8.learning` 4, the PX seats' learning room) once more: `DIGESTS_1019L` are the pins
  before it, which each pair still has with that row left out (`before_1019n`); every older table's helper leaves it
  out too.
- `block`, `BLOCKS`, `read_block`: THE DESIGN BLOCK of each document (the constitution's `probe` comment,
  docs/operations.md, league/equity/INTERFACES.md, CHANGELOG.md): the same sentences, whose figures are `figures` of the
  pair in force. `set_design` writes them from here and a test holds every file to them, so the two numbers and their
  rule arithmetic are the only words a design change moves.

Decimal throughout; rule arithmetic only (no figure here is a market's or an account's); standard library only."""

from __future__ import annotations

import copy
import re
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal as D
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from unittest.mock import patch

from league.constitution import CONSTITUTION, digest, money_digest

REPO = Path(__file__).resolve().parents[2]
ZERO = D(0)

#: THE GRID of the pre-registered study EQDONE-3: every pair `set_design` may be asked for.
SEATS = (3, 4, 5, 6)
SLEEVES = ("0.50", "0.33", "0.25")
CANDIDATES = tuple((seats, sleeve) for seats in SEATS for sleeve in SLEEVES)
#: A20's design (Oct 11, 2026): what release E1 deployed, and the rollback (`set_design 3 0.50`).
REFERENCE = (3, "0.50")
#: Each candidate's (money digest, full digest) BEFORE THE SEAT RULE'S BLOCK (release E5-S, e36c7e39), kept: a pair with
#: `equity_money.probe.seat` left out is still on these, to the last hex (`without_seat`), and the reference's pair is
#: E1's own (main at 7d2d3c84).
DIGESTS_E5S: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("7e41909a9da3e3f44cb4edd8f37921d7f6edba5a9de84e328624570d94ca146a",
                  "e909eb1040231bc078e878df2d87fad7a1001d86ab3eac32be5f45f2b82c1895"),
    (3, "0.33"): ("900917743dcfa53badb99798ac87d9c69a2b157879d174e621f3514ba8d4bd88",
                  "48f83ee82fbb68d8aa41b1043ab445a566f1bb3c315181f62a8147f6569d8650"),
    (3, "0.25"): ("3a7c52d58911d0c1a39f58cbe79547e343683a18004355b52a9390c8aec04fd2",
                  "6d19fddd271cc46682e48e09ae14364976b76077ca084198874f47dbf4340b43"),
    (4, "0.50"): ("5b687cf48fc6bac3c5b130de7e63dfc71590ed0fdc8c2597e93558b96c41ef3a",
                  "5c531714096750545488d6a8699aa6eeb151ce35f262ad62c3db70e2e6b46c6a"),
    (4, "0.33"): ("1661e03b67f35de873bcd9d7aa66d59807bc70cdfe51c964f99879113da8a3e1",
                  "973363b3f96bffe970b84389cee2f69c8ddcc37a66ce91db5659035a8618987f"),
    (4, "0.25"): ("25f5a13b3b70935186b4b498fd58562b46ee3a6cbec2111fff2b68aa3593492a",
                  "f5d7f330cb2887077c6b7d29fa986b0e8bb4d15b877865790171a6b0d682904a"),
    (5, "0.50"): ("1d4919ebf67f1305032c69396e842011a9aea6f8e2155fd630af552e3345945e",
                  "ebae2274d06c4f470597156c7d83b386ba10e0c4124376fc252021f57803991e"),
    (5, "0.33"): ("ae0509b148b9b4dec10850c51138defd2d3e5c8a3806c00a397aafc36fe519e1",
                  "6c376e6ccffb4f0813c475694fdd183c2c963dddc881d0f7736259114def32b5"),
    (5, "0.25"): ("50cd8863a7576a18bec5371f52cb1c2c12835cd8e9d4f4b6f7720fd224526704",
                  "2195caac2c2447ee48c9ab1cfdcd11be4eef1ce078c044159018e7c440869cf3"),
    (6, "0.50"): ("4c83f17710c59341057d3e83d69da4cc9b146b9822aebb471782121fc738d32a",
                  "4126365e37ed851f119c36f5340834ed7ee56d5cf477c658dfe66e0af9d910b9"),
    (6, "0.33"): ("e66a31c519ab8134a29fd042181c6827b7001fcc1bb7dd0b23d9a4a0a14a1a55",
                  "735e375e170edbb6c459ba30fdd42233ace6fb648f033b7023efd2cc1f5dedcb"),
    (6, "0.25"): ("6c0bc42b8715f5ff7131dfc95c4312ac05d3453ef23e4c4a31bd8cbb195cb8eb",
                  "c3c061b0e320135486a53aedcd375eefb6b8773c9550eaf8f3244453305153b8"),
}
#: Each candidate's (money digest, full digest) WITH THE SEAT RULE'S BLOCK AND WITHOUT THE PANEL ROW (release E5-A: the
#: rule "activity-1-free", the floor a quarter of the sleeve, ten idle sessions), kept: a pair with
#: `equity_money.panel` left out is still on these, to the last hex (`without_panel`). They moved once, with that
#: block, from `DIGESTS_E5S`.
DIGESTS_E5A: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("8c226cf185bbc426c390a893e82bba77ebfd9792fa058e662be258bb0dcb4081",
                  "def9f80f4027519268dc50ff336fe0d7160d28d5b97c0e4317ae21d512b696e1"),
    (3, "0.33"): ("8c6c0261b853befec6dd2b468489183baa88f17b7575ef9a909487f1a1b90688",
                  "c06fb24a1be9fbd482a9802ab71e03a0cbb87fe1deac55ed1eb13a691967f815"),
    (3, "0.25"): ("0734f77bb23c7f02955146989293f478a734ed5b508700b6e51486e53904c316",
                  "5d24a3cac46d562916b29413d8920bdf311ef4391872132a94c574b8ed72f14e"),
    (4, "0.50"): ("b9cf4cb2ffb61ca8db13d64835d23c5daf13f08516b83aaa4d6a220a9d71a07e",
                  "f303a85dbb6cc69b7124a2203944c967e8ea3eaf861b52633c1b3e5b663213b3"),
    (4, "0.33"): ("48e7ae65f93387a363106c6e52536e759e63af9160509185603f370ac3b620d4",
                  "61166f7f64aee1b0fea3ec0f3f7f1c1ea94afd83424880906c76760b5fbbf937"),
    (4, "0.25"): ("016027753f3a678fca4fa6248bf0218cf4652dc71fce5d890e3eb04ea94cfbc2",
                  "7d9f14ea8868beb210250f76bf4a5dd42b9dceeb810140a34d0416c6484eee6f"),
    (5, "0.50"): ("1dac1996e2e2c2980f4112caa15d3a4af512fd0d51bab89b74054402a525fac3",
                  "b76531a4b380631559981060b21731180e19cdbd01e0f3abc6946e4b9f83660d"),
    (5, "0.33"): ("1574adf70f54eef1bbdfe26200d6e678cfe136f0e12e4414fa9ab0675842b78a",
                  "26cad2b7c54a292afee4d0575055ea68c74e4bc0b4eee426a785fd9914850875"),
    (5, "0.25"): ("d7f347b9ba967cceea43ffc48d5c946a3a303336c49e80bbdbd6163780b2dcab",
                  "7f9bb7b74b11c7558c6190fcf0504804abdfa63732d82a9a45114e8022d5f411"),
    (6, "0.50"): ("5b95d73ea21df2e58d40c1017274e452b7ecdeaa54edd25bd0b2562ea30d6a64",
                  "4ef472e1cfac4124388dc06d95b5152ea2b9b129504ec69814ca7dfcab0af52d"),
    (6, "0.33"): ("0164574aa91df37fa55800e92247de4f1211fad964c5ee5af404078458a4e32f",
                  "d61bfc89c7bb76a112399c179959522d6f942b128db8ebeebfa7392bef0c28c5"),
    (6, "0.25"): ("11a1dc0cbe194f8609dd07340d5599725c87ecebf271b9a5016ab49c0a14156c",
                  "00c2bf6f2c57125e2b66e84730ab3a25c97e163438dc8e1085486d03ae69f4c9"),
}
#: Each candidate's (money digest, full digest) WITH THE SEAT RULE'S BLOCK AND THE PANEL ROW, BEFORE ONE OPEN STRUCTURE
#: A PROBE FAMILY (release E4 step two to release U: `options_money.probe.open_per_family` 3), kept: a pair with that
#: row set back to 3 is still on these, to the last hex (`before_opf1`). They moved once, with the panel row, from
#: `DIGESTS_E5A`.
DIGESTS_E4S2: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("46b933a93889c308beadb4e8f585fdfcc4d0780a1c6279992489291d68868e64",
                  "d9cf31491d72f7135b01fbb51b76cb15e9c9d70bc47c0c4c202c879aa0bb2657"),
    (3, "0.33"): ("f0097957e1250dc5f2b6039c127cceaaa2af75d27ba461d3d2116da7e3019fa1",
                  "4d9369f80656fcc5eb08b06bee4b8434c81075a18d6fab95f2c5457d4e2fbcf2"),
    (3, "0.25"): ("52d209a0c420738567ec0526e342860a0b69f79e6f0a429c40f6a524b925a9b5",
                  "d5780870f63d1f092112db59baeba4ce21b4cb22052289fb2d2be139ae9d3fd3"),
    (4, "0.50"): ("4ff5b549b395eb2cdf507b70cbd72e586a9dcda56008d0550a07532a1205a3aa",
                  "5e6e7fca42aad852494c190abcb32d88d5345955f75d0936f553ba749dfe5aef"),
    (4, "0.33"): ("099e53a68bb19604862f703d6974c61dfa762b602f79bdf164a0dceb7d75c8e3",
                  "5eda06cf7fa280acef15b62a091dec465d59ee5372cd91e582c3e6eff71ec4d0"),
    (4, "0.25"): ("77fd819c440f0f27ee97ba21c33c46af74f4e8ed6db990fe112bc52d9b375bfd",
                  "1f8cdd6b7c6f52e5c09b91bbd364aab44c6b74df5ea5e132a5aeefa4970e363f"),
    (5, "0.50"): ("954a02a88fb1ce0fdcde4a5bafbcfc3be71addd80cba760ebc21035802978c8b",
                  "5e0785efac2638de87139cb6ebc3f18a7dbc644fd841c0ab9e12a06e112dbc83"),
    (5, "0.33"): ("a29a973a6cc3b47321d564f25ac9fd99f47e3370414fa4143c3e78c0e183a158",
                  "ee4c1d72bc213649dddac5f23a0507e6ed2d8e24b2ff932a5cdf2456889af1a1"),
    (5, "0.25"): ("0b45ba34f44ccf14dc613c120d3fd515c0221dc883ea9a7dadbf6b1d2125555c",
                  "c4629841fe4e4461659cfb70ca1ddcacd16283952befb7cb5790090190e4a37c"),
    (6, "0.50"): ("de5ed74e5180f9ed6316f46b45941a57d00cacb2b12716738d095fccf909f582",
                  "111ede85f9b401c9af74f0f1967f9390c37ccd35a47f6fb048257db3c691ce6f"),
    (6, "0.33"): ("9ea2b4706d5b4a9e537bacb01e585a04eeae2f955973a414de22fd1e0f149f42",
                  "bf25c4dda6f6a08044a3f1c080fd0b95dec4d17b10b02a42568d57297e945001"),
    (6, "0.25"): ("405bf98e4411d437b87902db37781da9c5d7ba7018ef4bcb6a2adb8a81820d72",
                  "92369b0a5d678f5712e0a9b8b1b2b84b7a7a58d334913a6aa7b0d10b623ede8b"),
}
#: Each candidate's (money digest, full digest) WITH THE SEAT RULE'S BLOCK, THE PANEL ROW AND ONE OPEN STRUCTURE A PROBE
#: FAMILY, BEFORE THE OLD LANES' STOP (from Oct 15, 2026 until it: `equity_money.enabled` True), kept: a pair with that
#: row set back to True is still on these, to the last hex (`opens_on`). They moved once, with one open structure a
#: family (`options_money.probe.open_per_family` 1), from `DIGESTS_E4S2`.
DIGESTS_OPENS_ON: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("440d55721cd9aa5e8a6631c8db15402413405c77594b44576f2355b72d5c133b",
                  "c1370f468529dcb4f315a573db9acfcb1688c0a9ae32890658aa9411ffd22ad8"),
    (3, "0.33"): ("5f2d43d5d21db73b270c912fe71cd8aa078dbc1442bb73972fc5e5ea09062d16",
                  "79fd0c040cf3ed5e707247c4f13d519e7bed2635327801e3c7dd487eb80ccd41"),
    (3, "0.25"): ("bf2b415424a935c67067b796a56ff30b4badb27a6600fda819f0603b397709cb",
                  "36cc092b47ebeda40dc2495537a801073d2d0b0a6b566d01a7341b0147f33dc5"),
    (4, "0.50"): ("61da7d9d23341e05bf7434f13d059fda66111331f8f4bafb76a161d3a174a7ea",
                  "d1f35cafb186230a6f1d4c1753d1ea584cfcb8ec09509a88232a99ac569838a5"),
    (4, "0.33"): ("8bfb426dfda652c3fbfee539d1c7fe8eec42860745c05dfa2349df6d9cce3aa9",
                  "cb5443d31af06e33354adb46b6af0855671c55cf183ac192c4bf86c2225a23ef"),
    (4, "0.25"): ("93214331a868d940be1b2f692e290fd3d810eacfa16def92c2bf401e69d48230",
                  "56b71de8616846de884a57af5b7fd97341c4ae177061e2417fd3305b98904726"),
    (5, "0.50"): ("1ad9188411cae5d31a106328375f01ca839b7be2934c12896af943ad6e32633d",
                  "0866109889f4775cc4171e463effc05c1b5c6e3e87cb5a2e7de1ae0296e544a2"),
    (5, "0.33"): ("4a21670a0d97dd3d98755c91e04e77bd75b36bdb456136e1f4b500038b80d4c6",
                  "9c3b7e75e6203081231efc7903fea9b708d22cdda2eed6e60f56ea2e39df0eb4"),
    (5, "0.25"): ("7d88d8981622cf7cce478d3f4f723c0b63e1dbbeb8a96a176bbf0e70f6ae97a2",
                  "d913345c1038abb6e0088588e166cc9609e906cb9e214bbd90c1a66d897c88a8"),
    (6, "0.50"): ("cd579e5df97eb24086d01c32a906bd601ae79f93304394e4779f98388b08bda0",
                  "1e14c7f7b46b2e9619acc1df96601724ad758edfdcbacb840a8fbb878f654653"),
    (6, "0.33"): ("cfcc94b14973a174c522928012df1b3aea97dabda171679b1566841ecdb2de0c",
                  "60796aed0c82235b802fa925f865daf10d6eca6d355ddd80ae044380edd4d93d"),
    (6, "0.25"): ("5ea6f99f0978374d78ffad577e70574cef4b83314da8a7b0be72cc16031f633c",
                  "82a9a5a4d5feab292ea0fb72a0382db4d5d893be93695c905897f6939feb219b"),
}
#: Each candidate's (money digest, full digest) WITH THE SEAT RULE'S BLOCK, THE PANEL ROW, ONE OPEN STRUCTURE A PROBE
#: FAMILY AND THE OLD LANES' STOP (`equity_money.enabled` False: the owner's goal of Oct 19, 2026 and PREREG-EVL-1,
#: section 8), BEFORE RELEASE R2 (no `equity_money.event` block; `position_share.stock` 0.20), kept: a pair with R2's
#: rows set back is still on these, to the last hex (`before_r2`). They moved once, with the stop, from
#: `DIGESTS_OPENS_ON`.
DIGESTS_STOP: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("07d5b40b7ed02ec32e09ad1bcf0b534fb8ea0cf8cb7af7b95c6006027ac693c9",
                  "93bf3250525657b382083274609d788829af73adc354e685367eb69d73ba317c"),
    (3, "0.33"): ("2f040cd3fe0c9aaa8e3dcab188eb22186ce0dd38a9bf58e179cad2ee5ac7ea9f",
                  "dbc6c2d717671429ac4d5875ed0246b448a3db6e85838081c81a45ddaaffcacd"),
    (3, "0.25"): ("ce41b7f4b8a453aa976bf8cf1157ec5bb605b0a479f5e4952450e1c22159189b",
                  "54ab9196bd96d54b7d1b2ee572e585c4746fde0f57a110695211899edd0ae5e6"),
    (4, "0.50"): ("b7d1e37c1286b2c18b44456b2fd62a363022b6c472e96cf1143005c8a405e7c8",
                  "ce41ec31a5fcaad015e491e7de70fa1efaf2ce2f61dac9ea4a94348bac071c4c"),
    (4, "0.33"): ("cde08662c77006572f3279c312a0e54c3cefd421656c544e9b897fc8e066e0ec",
                  "b6b5128703885c617ceed9f11bbeee2f4987afba2276f751c50ad63fce508321"),
    (4, "0.25"): ("49e2f61c64f3bd1f6a03e1573829a43c4903c1f4a88232512dfd7baca76a8b09",
                  "12337eb02b7faeae4b060095fba277e99ea9480d74c23d23257003739cb4aa3a"),
    (5, "0.50"): ("36d4d4e38021d4b67ec6f734866da0e8bf5d55cd802492ce0492148fc8cf89e7",
                  "0ae950c868e47fed157cc48c1b189b0fc0ceec31c51d5a00dfa7ac0dedfef6d8"),
    (5, "0.33"): ("ae0b26fb56aa4cccb1402c8d35a150dd541e6c7f25a8c505622aeefbad20f82d",
                  "94fd4aaa77dc2e0633e1849e14f3f298d70791b5f7da5b8be22bbace5edb105b"),
    (5, "0.25"): ("b17359ad7cca515eebbe3bf1b332b25cfda177b4ee5488bbea8b538aed38fcc7",
                  "9efd2485fecab15be906e22dd3d7f4ee357d7c881e866fccb444f72aff246a43"),
    (6, "0.50"): ("27a118be23ad8b8fd7625171d24d83ea95653778e758193a0e2944adce73d824",
                  "2ff9868c5420ad6465e957725cf75db07e2119727d73e49753894fe79da11cad"),
    (6, "0.33"): ("5b05e6515a5580cdd2411bf8726d4d8910decba8c34be5d1564d05120a0efade",
                  "0106048c0b0079026fa95358275d395e8e2388db94ce8ca8f1598736e6db4172"),
    (6, "0.25"): ("f4fc39ff3b39635e7351c2f01cb0c84adf109a57d41f0eb0599d628dffa51117",
                  "34bbe7a594468a6b3ea12d3e96c4a8a6ed8f320936faa1a87d8cf4e66f31beeb"),
}
#: Each candidate's (money digest, full digest) WITH THE SEAT RULE'S BLOCK, THE PANEL ROW, ONE OPEN STRUCTURE A PROBE
#: FAMILY, THE OLD LANES' STOP AND RELEASE R2 (the event lane's real money, `equity_money.event`; `position_share.stock`
#: 0.10), BEFORE RELEASE 1019c (no `equity_money.event.max_orders_day`: the event kind's orders counted in the equity
#: book's one 60), kept: a pair with that row left out is still on these, to the last hex (`before_1019c`). They moved
#: once, with R2, from `DIGESTS_STOP`.
DIGESTS_R2: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("13b226ee982c53659467952d80bd4ec6ddab2e8835ae3d04b1294b49e082bd0b",
                  "9c0ca64d68978a19e32ecabc88530fc5bd52cb4f79ec18370767df7d52aa1b81"),
    (3, "0.33"): ("46274783979b972fc3f8dad523b414c7c4088ed0c839121a22125911a326a890",
                  "34dd3004d9fd1d6895435b1c583f43429b242541648ff8ae9551ccb4eb264ad2"),
    (3, "0.25"): ("ca6302ddac26c60b6cfb8808eed4d10b66219a19659e8da26512bf205f09c44b",
                  "3ac1eb975d258199ec9bb199fc18522cb67bc0a72145daca94ed3217ab899c26"),
    (4, "0.50"): ("e53a6f2b06defda4dc606871b888fd23c73562fcec107f15db896b5a5300f204",
                  "f1b00b1236de266d195a10e24bd735190806aa11b63200fa1f9db4fe66a58854"),
    (4, "0.33"): ("220e4d2b302a9c9c75c0c63b8ce61037ae453107d3805927b90efdf11cb9e1a5",
                  "d2f9e43d36dbf53dd4185a264a2a5c46000708b010712fabcbd615d57fc38199"),
    (4, "0.25"): ("af8150d24d4a1baa30840cd72187cedbe779370c5442cf5179a9ded16a19d875",
                  "ce934462d8e931f0137d7eb3e0d0bfec9c14517bd81ed1152eaab6a63ca62354"),
    (5, "0.50"): ("9785066fd233ac1cb3b162192948cf1f9bf541bf997db661c34c76bf9322c1b5",
                  "248656014077fb7cad3fe16419be4e22091e7d0bd35b1370d530fa2948061586"),
    (5, "0.33"): ("d79f41dd5a0bf19015b035d1e3c32c359a1264ede29e02be40ae1f829ba2aba1",
                  "61e1fd86a4926c6f16a74b665561876728ed1a4b8ddfdbf45b631851045fd401"),
    (5, "0.25"): ("87f428a8c60525cd3cceb5f69b0ccc5d39742648b153ab7adf9b6b99481ac958",
                  "d591286bd13a3b28f59a56f11f3a2884bb43e4f5a4eb3cdacd78da2e2e9dcefe"),
    (6, "0.50"): ("3fa2875d80acac4aeaf197ea90b9416e0233e1da203088a7654e769f023f3145",
                  "41a68261dca21388d98b74c639d2d48c72d2f271ba296d0f565fb36f84241fb7"),
    (6, "0.33"): ("ec1de2827a25bdc0887cbf620129b10f07814b6a7e536c2cf9edd139bbf636b5",
                  "61a05e31dacda1c94d832d0b7fbc25579db2031adae259a474402f863cd7a438"),
    (6, "0.25"): ("285fa7af0f3d99769fe3b06b30c04d98be1f9f7682699ca3359e6e4777bf807c",
                  "fd38e4e1fe9f9485bc1554045a7c03fb945a278313320aeccce45c4f2ccf6232"),
}
#: Each candidate's (money digest, full digest) WITH THE SEAT RULE'S BLOCK, THE PANEL ROW, ONE OPEN STRUCTURE A PROBE
#: FAMILY, THE OLD LANES' STOP, RELEASE R2 AND RELEASE 1019c, BEFORE THE CAPTAIN'S A86 (the Probe band at PREREG-EVL-1
#: section 8's 5% of E, at most 6 open, one share up to the name's wall), kept: a pair with A86's rows set back is still
#: on these, to the last hex (`before_a86`). They moved once, with 1019c's row, from `DIGESTS_R2`.
DIGESTS_1019C: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("8581de707eb39e8c175dcca22fd79771ded156fcd2f29dee4984a4ca2cf0f179",
                  "c9515d5fd22405677acf1173aa966a1f63411431805ff18faf72a4616f296faa"),
    (3, "0.33"): ("d607467573b6f38445617b53ce96032f7b3e686783fa84d1153445a05183e338",
                  "a7d8060acea5386f5e186de7b2ae335aaa0b28ebcca2f4f3d4e6935070f60f7d"),
    (3, "0.25"): ("6412b918c638df3c189fe608d13388da156aa785d7f0aa9ff0614044e4382760",
                  "f282c1056d29405a7668f7e856d445537cbf10ea7de360351a82187cc1349fcd"),
    (4, "0.50"): ("721efdcc5dad3b5e553822a79c6e97e2a36eeee5f22ade04a9bfa6b7569ca7f9",
                  "9ad5a7e8c661c8bb152b01b6631040b298908141f7d332bb144e0917ad682eac"),
    (4, "0.33"): ("29f409366e1c736dc91c3078f669c74dfcd390c90f7447e27d53758187020d2e",
                  "f3277db0bce2b41e10da65d03a5dcecbde7a40279c1088ec7b65294f56afff57"),
    (4, "0.25"): ("f99c437a2288301062877d62888db3a7ae0ca991f767ab8f88ebb205641d82ec",
                  "f7bd8eacab4d579657e15f7ccc106db41fc32c121aa5b3256638def7a5febc39"),
    (5, "0.50"): ("7d1eb95664b30a538a0511a70d7886230144abf8edde6d7ab64d0c95e95c88b5",
                  "c9b8069f2a78e20c03d51196889f60642dc3500bfa6380592e9a1f394a7f200f"),
    (5, "0.33"): ("de3c81a28d3088e5ab999f81fd148a6359b73fb9c0c5af65854bcd1e701d78eb",
                  "892c0934d027dd26e0c1e3fb3a03d2f048a37cdfcf9674d60ef1ac06ebb46581"),
    (5, "0.25"): ("4f3c474dceaa334175f1f0772d99dcfa6f3e46ad91f89ef5dc42a7b9615e1a48",
                  "364423f1c6127b1981c33d1a29e4df412e357dec8863c306aba27513ed1dd98e"),
    (6, "0.50"): ("f9b909f2d46ffd715858ac22807149f143c07bc33430eef930a0485b1ab476a8",
                  "3a3e30be42183c9f014009c1ab7692de27f13516fd74f098799bf48bae6c2290"),
    (6, "0.33"): ("af7aebfed143e4dad9941f9223dca1164938ab0859e512694b0688ba9ed92ce1",
                  "1c32fe287901168cec2a462e51a829af591a3d25353fe6beab0fc0bc6ffdc845"),
    (6, "0.25"): ("055e5313fb05244d32361e539e580efa7354881222e91725b097f8029311528a",
                  "a8d4cbd908b7730daf11294ddd9e1db7dbf0eb5c787ef44b72193a740291cd86"),
}
#: Each candidate's (money digest, full digest) WITH THE SEAT RULE'S BLOCK, THE PANEL ROW, ONE OPEN STRUCTURE A PROBE
#: FAMILY, THE OLD LANES' STOP, RELEASE R2, RELEASE 1019c AND THE CAPTAIN'S A86 REVISED, BEFORE RELEASE 1019h's ROWS (the
#: captain's A97 S2 and A100: `equity_money.event.reach_bar.probe` and `.sized`, Done's size bar a Probe or Sized buy
#: rounds up to), kept: a pair with those rows left out is still on these, to the last hex (`before_1019h`; releases
#: 1019f's and 1019g's, `PINNED_DIGEST` of 24f73f18 at the pair in force). They moved once, with A86's rows, from
#: `DIGESTS_1019C`.
DIGESTS_A86: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("7709cadb7ef4188a0d5416d4ea2f719e44258163ab9b9e1e3dbcf9c0c3d54a02",
                  "5e450ade47d49a50118253a57e5840f06fbde3c39de65788d542c633ee406d3e"),
    (3, "0.33"): ("6015de683c4363dada4fcf51456536d7bc277d13613329a3acddec95d12bf901",
                  "311d61bced3613e7f4403dcd46b08f5464e4e5a3b2a4ef7356e80a81916c7271"),
    (3, "0.25"): ("7682d71ef8bb3562b10ac3bd9d79e91005ef2f1e08350c8e378b8fa9ff5718af",
                  "25fcf59fb7a7ce08bb444076923e84f927c98739b38727f5ce0f2b8867ce0d6b"),
    (4, "0.50"): ("aac7109b6841d32c0dc8defa865e5242e4afdeb6c1988d57efb915796ec2c07a",
                  "47aa59c09dbb802bb467ddd8521b7892e857cf58ca6e7543727fc30a00b8b77d"),
    (4, "0.33"): ("045026b2ccd5b0f0744cae7bd9b599b256450b8df08d20359e3b0f71820ca3b7",
                  "2da0280bfbb44f0ca4a4e3d77e3e7c92461cc70c564c8d09fc2193793cc9af0b"),
    (4, "0.25"): ("a5f43a571b43b8905d67b8107e5b9d7c93b20d1f80e52ed51c61ae4b0d75a265",
                  "868d5ae9454b889a408b859209f11edae3ea910d2e5c687ac13b9b64a769746c"),
    (5, "0.50"): ("3ffa67d383105fea423047e4084ee54ffad239c587422cedf6965925bbb87301",
                  "9b8f7ec0edf5d60c0e3771ef5fcd21879bf36e2347b6bbb6b61ff85600dd14d6"),
    (5, "0.33"): ("e0a77b3587dadb76cfaeb35d978c02f16457a07c809051a4182d8307bbd8deb2",
                  "4a747b442e99186583ef58605ef547831ee58a4a24c4edca640432cb0a293e26"),
    (5, "0.25"): ("114a34952d7f6af601deb44c4ea7e51509d2ec59d588c4ce6e63a820c466b5e9",
                  "aff61c9090a0d53526c3353a037c33ac059cb454070c045eb042d515b808ea1d"),
    (6, "0.50"): ("4fb3c67b4cf691a6268eb69f5c8b52be21d3c7da25cc5db75d7bbddf16af81cc",
                  "a5d78f40efbb13fe0bf07287c622befea754703e8ae8afba635acf6b64a464e5"),
    (6, "0.33"): ("8b35532fd9c322e3002af22b9efe21429e9bb0d6982737341ed4c87553258c8d",
                  "67549da64a991abceb5525f6e526721006607895a70f6cc3434c4e5dfc51cd6f"),
    (6, "0.25"): ("c2f0a4787b094906090a98ea12e619acbeadda709cdbbf159c9f171263133918",
                  "24f73f1876b6e6451061248b29b2aa38df3d4df19836c81a4edcaa63bc492716"),
}
#: <r2-digests>
#: Each candidate's (money digest, full digest) WITH RELEASE 1019h's ROWS AS THEY STAND, BEFORE RELEASE 1019i's ROW
#: (PREREG-EVL-6 section 6, the captain's A99 and A100: `equity_money.event.max_open_v6.probe`, the Probe slots of the
#: versions registered at or after REGISTERED_AT_6), kept: a pair with that row left out is still on these, to the last
#: hex (`before_1019i`; release 1019h's, `PINNED_DIGEST` of c3026eba at the pair in force). They moved once, with
#: release 1019h's two rows, from `DIGESTS_A86`.
DIGESTS_1019H: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("ba9e634107e28b5d31dda4de7be77463db6c2f842a7731e02571fec4cf8ead08",
                  "50f572ae5e07b2c28112dcc534305563136cb664a1cca6980ad2bbb987e823ce"),
    (3, "0.33"): ("be924ec0acad547dd0e0742d1b665196e48c929788d55eb86c08dc96925bce9f",
                  "998d9c25689cd066751a809fae8f3eb501d4c42be07174ebe555f4415ee1dbe6"),
    (3, "0.25"): ("1b60c837e8b47251f6ca645bf457b980c45f377b2dc0cc8823024b852be8cc16",
                  "c9376e9d629548a1b3e4252cd941fa101386f22cd74048d94e8d23811a1e11d0"),
    (4, "0.50"): ("7cc370a9c70de43cc28f672608048aa42df80a31e21763f568d95a71089c45f2",
                  "3e3f7294c21128fde31e7d864a3491419b42dc36377c6ae80a1d878290c57b05"),
    (4, "0.33"): ("eb5e79a8d96726698ac45304795ff569a085a72e71ad6d36eb95a420b2a1e9ce",
                  "88789909f122fd5a6fc233755f2836d36e0b2fbee3994c78320d40528e6d2262"),
    (4, "0.25"): ("8c08a8700ccc686176cc09993dc23b1ac7753ef0048a1c4545f63a2d0f42471d",
                  "8c5603d47994193de3a5198ff19f658f3013a6edaa174cc198acc2443571fed7"),
    (5, "0.50"): ("e7067b8be9d9555a61561567b78f1f5993a9908da899e6694dfbb5476ebc7f7b",
                  "6da099d821f8eeb75db4d5d3cda51c053fb6cff1ce761f27c6f7315dd589deb3"),
    (5, "0.33"): ("e03f803656e36caec14eb66b198378ae81820655144c1992e5f456557e616b6e",
                  "58e46470c27b6339ca9ef4494e308d5596c1ba417ccbe73de5bfd83b8c659187"),
    (5, "0.25"): ("a437b19784600b794a1ec78c84358888c42ea5b5e7e9bce623c0d7f239ade2b1",
                  "aecaeca28de5756ce418153ac7f8dd5a4b2cb0e1ebe7d78e8cb0db9181b5146b"),
    (6, "0.50"): ("e521515cfdde14152f07ea1aab968883ad67b694f193e957407feb83ee85434f",
                  "36e7b51f9b376d87ac5814aac46d3ccc9d2d60c0c10b0b7a231464a2233bf4a5"),
    (6, "0.33"): ("03c967b350625548fa22bdb6657fb1b93905e647eb4286c207945b47b572d564",
                  "94b55a05b3a0fbc3d38ff296ab481155acd2d7366197e1f9ec79debd60e3f9cf"),
    (6, "0.25"): ("8e63ce64af3d16b410d4a8af3521f4ff16948a97f13fbb8aa59e197983f47a7c",
                  "c3026ebacddf03bc853d7dc1f1b64d5788ecdd9dd90623adb2e6365baf9e9f53"),
}
#: Each candidate's (money digest, full digest), pinned, WITH THE SEAT RULE'S BLOCK, THE PANEL ROW, ONE OPEN STRUCTURE A
#: PROBE FAMILY, THE OLD LANES' STOP, RELEASE R2, RELEASE 1019c, THE CAPTAIN'S A86 REVISED, RELEASE 1019h AND RELEASE
#: 1019i AS THEY STAND (the event lane's real money, `equity_money.event`, with its own day order line
#: `event.max_orders_day` 150, the Probe band at 3.5% of E, at most 6 open, one share at most 5% of E (A86 REVISED),
#: Done's size bar 0.8 for a Probe or Sized buy's round-up, `event.reach_bar` (A97 S2, A100), and PREREG-EVL-6's 14
#: Probe slots for the versions registered at or after REGISTERED_AT_6, `event.max_open_v6.probe` (A99, A100);
#: `position_share.stock` 0.10: the owner's goal of Oct 19, 2026, item 4, and PREREG-EVL-1 section 8): the grant
#: re-ratifies on the first, `PINNED_DIGEST` is the second. They moved once, with release 1019i's row, from
#: `DIGESTS_1019H`; they were regenerated by the tree's own functions (`money_digest` and `digest` of `constitution_at`
#: each pair, what `set_design` checks a pair against), and `set_design` at a pair lands on its pin here.
DIGESTS_1019I: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("ba53220464d3934875f8fb325f750fb9ccd1dd971e54701fd875c7f9d67642a3",
                  "30aceaf8696ce6a08adf86e07490110368760e761e63ff0e82acdf9b95e68bbd"),
    (3, "0.33"): ("545eac71ac67a12aa848dc29913907208226b1c776d3a0a4dcb84088468db07b",
                  "74cb05b6656fe3877617681cab082cc511f012be4250220fa23aaf4f64f6c58b"),
    (3, "0.25"): ("47a339fa0b9eef9bb706530afcbf54c08f681effeee25400d0b0b60803f49b22",
                  "7467276b4ddddcb8b2571b6011cdef0dcd3de02fc0b1ebcc2578a067248fe0eb"),
    (4, "0.50"): ("6df64790cb8c67477228931ebf36ba4a27d001ca7cc35bced31dc899dd4dd4f3",
                  "5df83e3d85b28f3fd3699523237a2a247982302ddf13d990af96eab63bc1374b"),
    (4, "0.33"): ("6e43b6f9a4f2b58f35b0ea8651b8e6496b92f98edd7dc856bde18e6e35cb3ee4",
                  "535beae3ad61906fdaa7b388884a0ca79a9183b3f1c486cf4d2675c2dcdf0a7b"),
    (4, "0.25"): ("adef6c8584644fba436826abceac4918e7e1032ff628f1713c998115ad099421",
                  "9973b3291b2931269fc35910081d6e57a2a5489160a6381453e55c5fffd46e04"),
    (5, "0.50"): ("3018fef4358dbf059992dc9e480f15f692079959c10726b3642c90ec5af15957",
                  "a9827192584496a1aa13d0efe84bddb634f7299fbc234d2a84b85f8a980c3309"),
    (5, "0.33"): ("1ae71a3643193805117fba4cab1b754c0baab0bcbf9668ef2d129a5094695272",
                  "db8f4e71768f6ed84c842f157d3b8ecc02e6b9b319bda050e5f73d9c8006f5ac"),
    (5, "0.25"): ("68553b86d1768c066fb48a24c8cd88d4932b07069179dcb0ec9585c666fa85b1",
                  "de152953cc5e1e8c8cf66aa9246d21ea2a3046417ec5e7b851c6e1b20d2dc052"),
    (6, "0.50"): ("bfab9dff79c686bf95be42b910be5315894a743392e79aa3f7eb737352d9494d",
                  "2c777a31859074f356802a2873e62c88861a0a16b097af95719c091bc43a6136"),
    (6, "0.33"): ("4aa36c13e1a8f8b20753f23210cec0e9c5631760f8bf7add4c75bc14ce63797c",
                  "2eeff27e7180176e1b2aa63965cc5a3d2ab0029d75fed7aedf780970287108bb"),
    (6, "0.25"): ("d52a5af5b3c6758232b2779143d4998752365bcadb9ff0678bd1b6ec47b38fc4",
                  "9c8b2221396c88f9ea8cb51c57f4e0060ffb07bfd859f1d945617c0f23b9412d"),
}
#: (`DIGESTS_1019I` above: release 1019i's pins, kept: a pair with release 1019l's rows set back is still on these, to
#: the last hex, `before_1019l`.)
#: Each candidate's (money digest, full digest), pinned, WITH EVERY ROW ABOVE AND THE OWNER'S GOAL V3's ROWS (the captain's
#: A138, release 1019l: `equity_money.event.position_share.learning` 0.05 and `.probe` 0.05,
#: `options_money.probe.loss_budget_usd` and `.loss_total_usd` 1900, `options_money.daily_stop_share` 0.25): the grant
#: re-ratifies on the first, `PINNED_DIGEST` is the second. They moved once, with those rows, from `DIGESTS_1019I`;
#: regenerated by the tree's own functions (`money_digest` and `digest` of `constitution_at` each pair).
DIGESTS_1019L: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("baaa5ad63fcadf0ec5d5e4dd2d504287d906a1b54338b2d722653da69bed988a",
                  "e865fed58236773b161bbe8a76a658e1dd5e2476dd5fa72e583eabf2e1960d26"),
    (3, "0.33"): ("85f6da88706282c471ec8e217ccf8e695cea217c3569aa935111e3cd93c324b2",
                  "14e53d3e9d7a1f4787659efed15e54996da3bbd190947c224f37a02fc8597422"),
    (3, "0.25"): ("dfb6d84263fdf5ea130f04a72269a52b187832bdb44ec405d35c73d31e0d18ee",
                  "3eb91bddf41773ca088876c0da8150d7af591d541f34bf13e53c0861b199d038"),
    (4, "0.50"): ("d7e193dfe152def498c90ba772cb4a443ca3821a24f02f5fa181034caebf86af",
                  "7bbe8a6c0147a62800051815bf99233b49114766fe2e55ff7fe9c105ae723242"),
    (4, "0.33"): ("485baccfb21cca4c2b02f6d36e373c580a405c5b2ed6fd251ef8b0fe70f9751a",
                  "80a6140c365a41d7c0bab5c3ab1c496225f9656bbc7bc9b3ce9700d04ac9b54b"),
    (4, "0.25"): ("cefa0e5b009df93d9c5a057e8e6a213fa33fd1ec4f9125ea85f14aee3d6e3f0a",
                  "d7481aea10f161a9176af45454be1d93117a2bb76d01d4aa96a88f02444e8b57"),
    (5, "0.50"): ("4f5dfdbaf2a5b8cceac5a37e01dd0af029e776fcd41a0ebc889fae26ae873778",
                  "63588fbbe912c9fd3ea34a14660e42073c06ff5d7254c34fcd48321fc12004e5"),
    (5, "0.33"): ("922d3b1775e9e61b0d005bc8d75d14b0fa1ad08cb48ef4c5d320a1a1e0906bf4",
                  "fd549a1b569da0ffd8d8140231df9be9f9c34bbb92d45f823d13a46da66c3f9e"),
    (5, "0.25"): ("679ce651e4ca8e3dee949fe2ef89dd4e85afb1cbeecd844afedb80d71aa1a893",
                  "726a012d79e9eea7b79ef716884f5aa9d96b24b275f60d5744fe8990cf298446"),
    (6, "0.50"): ("f63cc4fe1787dfe7db896edcefbab77c9b23c7c63b26dbf8d39501b1a2351d14",
                  "090aff364944986c7e5ca7c12e208a1a6e990dd9400819bd033ff43d7603cc00"),
    (6, "0.33"): ("7a33bda23216f8c2284b956e3d75593054cd8e53561fdbaad3ac60cb84487969",
                  "81ef8cb7550b3218ce783c45a19736259857fa21a332fa1dd08426058bc95488"),
    (6, "0.25"): ("1687e4e34c63d9096bb876195a15014f47e6efddd567bf43d85696a92096e80b",
                  "3feab26da60f48ac72d156b81f02261ffb08556adeeb97ccb1f922ab74c12614"),
}
#: (`DIGESTS_1019L` above: release 1019l's pins, kept: a pair with release 1019n's row left out is still on these, to
#: the last hex, `before_1019n`.)
#: Each candidate's (money digest, full digest), pinned, WITH EVERY ROW ABOVE AND RELEASE 1019n's ROW (PREREG-EVL-8
#: section 4.1, frozen at A122: `equity_money.event.max_open_v8.learning` 4, the PX seats' learning room): the grant
#: re-ratifies on the first, `PINNED_DIGEST` is the second. They moved once, with that row, from `DIGESTS_1019L`;
#: regenerated by the tree's own functions (`money_digest` and `digest` of `constitution_at` each pair).
DIGESTS: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("92bca93bbdb6abdb6d47fd93257ff78e5cbf2b4d23442b1f0c42ae6094951974",
                  "779ca4d750925b9798c3aef03eb30d122d160f938e4ad4bfd856b97868caee29"),
    (3, "0.33"): ("7c2f1645c0ef5bcc5ab019afac4cd31ee58d6ffb8b7bd56f95068d90da6f5b09",
                  "835847787f0d71a501eab23482b17a826c1086f2591ea14b6f6b46d42b177949"),
    (3, "0.25"): ("334b5ed4bf879d701313f917af43d7bbe24b11b21efe7d23b9f91e85fc07913a",
                  "271f37422845f609c43a988af2efc1727cd95c6992db5f5d30ae923583dcebe1"),
    (4, "0.50"): ("d1aa4f23c019d3ec823707bf08d8700423da079105d5577869444b8aa7f2bc23",
                  "8243537789010a3832cfba706d063c7169055db92a7d492b6273c27a9311dfd8"),
    (4, "0.33"): ("11673faf6f0054cdd828a52c189667c992d81dd2d7b29a6fd31cff11f5dde07c",
                  "025d516c691764cdd9a101db6a18f9ea72d3be205eacc3c0d11a3329d02c1741"),
    (4, "0.25"): ("c3670bd37170f6880d1f914a1226614518b215ca7d9981fce9d23b3d3da0d4df",
                  "1fa7593e6861be3d5890b63a9a924b13e8fda4dae01f288380c5a4f81620c195"),
    (5, "0.50"): ("53d3cf45a834c98f7e93b0aac8b1a35f03d93437b55c755a5d11f943841787c5",
                  "cd343d4881e1912f651c7a172e867a2273dbc7c8c3610ea2a7a65f851f632ccc"),
    (5, "0.33"): ("de63c534c04f49493b0be89cca713d1d039ca480a2f1ce939ff058eb0aeede6e",
                  "7dfe12c228668f333e2f68444b1794a4a1df68735e3e04260455e34bbf021d98"),
    (5, "0.25"): ("9b407e3c58ebcc7f709e551df44859da74c98823ed2dbbb6f0eb839e44c5f221",
                  "e156daa78f808b08bd467550b1dca8cb9bb22eecea7a2c907367e3f21ba925e5"),
    (6, "0.50"): ("6799b2d95dc127a69c0a7110fb063446287b69f9b575dda07dd5f9205d25a6f3",
                  "c7589d05c2e4e24ab3cc350b812b845ac24e17cba8b8291510aa9ff10c0249b9"),
    (6, "0.33"): ("8a1d66b80c8deda95dfe16ec7ef319fd3c7ac41d9707e64a6aab182fd496c5f7",
                  "c3254b8c20b48ae165e121e63e0dff872f9602031233238944e896ac2dddfd38"),
    (6, "0.25"): ("77c3cfedc0e9ca6d2e6b106dad46cc3081f7ae1dac9d0a15c5e0313c522eee11",
                  "138ee8eb8aa3a54b1633a87e3f9499b3a6d78e28adce97cbe1aed26167e846ca"),
}
#: </r2-digests>
#: A share is floored to this many places of a share (league/equity/config.py `QTY_PLACES`, read here as a figure).
QTY = D("0.000001")
#: The order two caps that tie are named in (the sizing module's docstring, steps 3-7).
CAPS = ("instrument", "sleeve_cap", "sleeve_cash", "invested", "cash", "budget")


# ------------------------------------------------------------------------------------------------------- the rows
@dataclass(frozen=True)
class Rows:
    """What the rule reads: `seats` and `sleeve` (the two numbers), an ETF's share (`etf`: of E for the account, of the
    sleeve for a program), the invested share, the cash reserve, an ETF's open-risk weight, the shared budget's window
    and total, the minimum order, and the collar's two ends (basis points)."""

    seats: int
    sleeve: D
    etf: D
    invested: D
    reserve: D
    weight: D
    window: D
    total: D
    min_order: D
    sized: D
    entry_bp: int
    max_bp: int


def rows_of(constitution: Mapping[str, Any] | None = None) -> Rows:
    c = CONSTITUTION if constitution is None else constitution
    em, budget = c["equity_money"], c["options_money"]["probe"]
    path = em["order_path"]
    return Rows(seats=int(em["probe"]["max_programs"]), sleeve=D(em["probe"]["sleeve_share"]),
                etf=D(em["position_share"]["etf"]), invested=D(em["invested_share"]), reserve=D(em["cash_reserve_usd"]),
                weight=D(em["open_risk_weight"]["etf"]), window=D(budget["loss_budget_usd"]),
                total=D(budget["loss_total_usd"]), min_order=D(em["probe"]["min_order_usd"]),
                sized=D(em["sized"]["sleeve_share"]), entry_bp=int(path["entry_collar_bp"]["etf"]),
                max_bp=int(path["max_collar_bp"]["etf"]))


def in_force(constitution: Mapping[str, Any] | None = None) -> tuple[int, str]:
    """(seats, sleeve) of a constitution's `equity_money.probe`, the sleeve as the row's own string."""
    probe = (CONSTITUTION if constitution is None else constitution)["equity_money"]["probe"]
    return int(probe["max_programs"]), str(probe["sleeve_share"])


def constitution_at(seats: int, sleeve: str) -> dict[str, Any]:
    """A copy of the constitution with the two rows set, and nothing else moved."""
    c = copy.deepcopy(CONSTITUTION)
    c["equity_money"]["probe"]["max_programs"] = int(seats)
    c["equity_money"]["probe"]["sleeve_share"] = str(sleeve)
    return c


@contextmanager
def design(seats: int, sleeve: str) -> Iterator[None]:
    """The constitution in force patched to a pair for the body (the two rows; everything else as it stands)."""
    with patch.dict(CONSTITUTION["equity_money"]["probe"], {"max_programs": int(seats), "sleeve_share": str(sleeve)}):
        yield


def reference():
    """A20's design for the body: three seats at 0.50 (`REFERENCE`)."""
    return design(*REFERENCE)


def without_seat(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of a constitution (the one in force when None) with the seat rule's block and the panel row left out:
    the table as it was before release E5-A."""
    c = without_panel(constitution)
    c["equity_money"]["probe"].pop("seat", None)
    return c


def without_panel(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of a constitution (the one in force when None) with the panel row (`equity_money.panel`) left out and the
    options Probe's `open_per_family` back at 3 (`before_opf1`): the table as it was before release E4's step two."""
    c = before_opf1(constitution)
    c["equity_money"].pop("panel", None)
    return c


#: `options_money.probe.open_per_family` before one open structure a Probe family (Oct 15, 2026): every older table's.
OPF_BEFORE = 3


def before_opf1(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of a constitution (the one in force when None) with the options Probe's `open_per_family` back at
    `OPF_BEFORE` and the equity opens on (`opens_on`): the table as it was from release E4's step two to release U
    (`DIGESTS_E4S2`)."""
    c = opens_on(constitution)
    c["options_money"]["probe"]["open_per_family"] = OPF_BEFORE
    return c


#: `equity_money.enabled` before the old lanes' stop (the owner's goal of Oct 19, 2026; PREREG-EVL-1, section 8): every
#: older table's, from release E1 on (the captain's A10.2: the switch shipped on).
ENABLED_BEFORE = True
#: `equity_money.position_share.stock` before release R2 (the goal of Oct 19, 2026, item 4, "<= 10% of equity per name",
#: set it to 0.10 with the event block): every older table's, from release E1 on.
STOCK_SHARE_BEFORE = "0.20"


def before_r2(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of a constitution (the one in force when None) with RELEASE R2's rows set back: no `equity_money.event`
    block and `position_share.stock` at `STOCK_SHARE_BEFORE`: the table as the old lanes' stop left it
    (`DIGESTS_STOP`), and R2's rollback of its money rows."""
    c = copy.deepcopy(dict(CONSTITUTION if constitution is None else constitution))
    c["equity_money"].pop("event", None)
    c["equity_money"]["position_share"]["stock"] = STOCK_SHARE_BEFORE
    return c


#: RELEASE 1019c's one row (`equity_money.event.max_orders_day`: the event kind's own day order line).
EVENT_ORDERS_ROW = "max_orders_day"
#: THE CAPTAIN'S A86 REVISED (20:30Z Oct 21, 2026: Probe smaller, inside the trade-less envelope): the Probe band's
#: rows before it, PREREG-EVL-1 section 8's 5% of E with at most 6 open (`event.position_share.probe`,
#: `event.max_open.probe`, which A86 REVISED keeps at 6); `event.one_share_max.probe` is A86's own row (before it, one
#: share at Probe went up to the name's wall).
PROBE_SHARE_BEFORE = "0.05"
PROBE_OPEN_BEFORE = 6
#: The rollback pair with A86's rows in force (`equity_money.event.enabled` False: every event buy stopped, the rows
#: kept), the first eight hex of the money digest and of the full digest.
A86_ROLLBACK = ("fd9e90c0", "005745e9")


#: RELEASE 1019h's rows (the captain's A97 S2 and A100: `equity_money.event.reach_bar.probe` and `.sized`, Done's size
#: bar a Probe or Sized buy rounds up to; release 1019f's floor rounding had no row).
REACH_BAR_ROW = "reach_bar"
#: The rollback pair with release 1019h's rows in force (`equity_money.event.enabled` False: every event buy stopped,
#: the rows kept) and THE ROUND-UP'S OWN SWITCH (`event.reach_bar` 0 for both bands: release 1019f's floor rounding,
#: every other row as it stands), the first eight hex of the money digest and of the full digest.
S2_ROLLBACK = ("973aa2e9", "3e8cf1c8")
S2_OFF = ("adf52674", "fe5d87b7")


#: RELEASE 1019i's row (PREREG-EVL-6 section 6, the captain's A99 and A100: `equity_money.event.max_open_v6.probe`, the
#: Probe slots of the versions registered at or after REGISTERED_AT_6; `event.max_open.probe` keeps 6).
V6_SLOTS_ROW = "max_open_v6"
#: The rollback pair with release 1019i's row in force (`equity_money.event.enabled` False: every event buy stopped, the
#: rows kept), THE ROUND-UP'S OWN SWITCH with it (`event.reach_bar` 0 for both bands) and THE NEW SLOTS' OWN SWITCH
#: (`event.max_open_v6.probe` 0: no PREREG-EVL-6 Probe buy), the first eight hex of the money digest and of the full
#: digest.
ROLLBACK_1019I = ("f87d7342", "134d6285")
S2_OFF_1019I = ("96d986c9", "8f9abf99")
V6_SLOTS_OFF = ("51625225", "f288d8ec")


#: THE OWNER'S GOAL V3's ROWS (the captain's A138, release 1019l) and what they were before it (release 1019i's).
V3_ROWS_BEFORE = {("equity_money", "event", "position_share", "learning"): "0.02",
                  ("equity_money", "event", "position_share", "probe"): "0.035",
                  ("options_money", "probe", "loss_budget_usd"): "400",
                  ("options_money", "probe", "loss_total_usd"): "800",
                  ("options_money", "daily_stop_share"): "0.35"}


#: RELEASE 1019n's row (PREREG-EVL-8 section 4.1, frozen at A122: `equity_money.event.max_open_v8.learning`, the PX
#: seats' learning room, bounds 0-4; every other program keeps `event.max_open.learning` 8).
V8_SLOTS_ROW = "max_open_v8"
#: The pair with release 1019n's row in force and THE NEW ROW'S OWN SWITCH (`event.max_open_v8.learning` 0: no PX
#: learning buy), and the rollback pair (`equity_money.event.enabled` False: every event buy stopped, the rows kept), the
#: first eight hex of the money digest and of the full digest.
V8_SLOTS_OFF = ('2d112ae9', '992cefd8')
ROLLBACK_1019N = ('93bb7e4a', '520fb41c')


def before_1019n(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of a constitution (the one in force when None) with RELEASE 1019n's row left out (`equity_money.event.
    max_open_v8`, `V8_SLOTS_ROW`): the table as release 1019l left it (`DIGESTS_1019L`)."""
    c = copy.deepcopy(dict(CONSTITUTION if constitution is None else constitution))
    event = c["equity_money"].get("event")
    if isinstance(event, dict):
        event.pop(V8_SLOTS_ROW, None)
    return c


def before_1019l(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of a constitution (the one in force when None) with THE OWNER'S GOAL V3's ROWS set back (`V3_ROWS_BEFORE`)
    and release 1019n's row left out (`before_1019n`): the table as release 1019i left it (`DIGESTS_1019I`)."""
    c = before_1019n(constitution)
    for path, value in V3_ROWS_BEFORE.items():
        node = c
        for key in path[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, dict) and path[-1] in node:
            node[path[-1]] = value
    return c


def before_1019i(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of a constitution (the one in force when None) with RELEASE 1019i's row left out (`equity_money.event.
    max_open_v6`, `V6_SLOTS_ROW`) and release 1019l's rows set back (`before_1019l`): the table as release 1019h left it
    (`DIGESTS_1019H`)."""
    c = before_1019l(constitution)
    event = c["equity_money"].get("event")
    if isinstance(event, dict):
        event.pop(V6_SLOTS_ROW, None)
    return c


def before_1019h(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of a constitution (the one in force when None) with RELEASE 1019h's rows left out (`equity_money.event.
    reach_bar`, `REACH_BAR_ROW`) and release 1019i's too (`before_1019i`): the table as A86 REVISED left it
    (`DIGESTS_A86`; releases 1019f's and 1019g's)."""
    c = before_1019i(constitution)
    event = c["equity_money"].get("event")
    if isinstance(event, dict):
        event.pop(REACH_BAR_ROW, None)
    return c


def before_a86(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of a constitution (the one in force when None) with THE CAPTAIN'S A86 set back: the Probe band at
    `PROBE_SHARE_BEFORE` of E with at most `PROBE_OPEN_BEFORE` open and no Probe one-share row, and release 1019h's rows
    left out (`before_1019h`): the table as release 1019c left it (`DIGESTS_1019C`; releases 1019c's and 1019d's)."""
    c = before_1019h(constitution)
    event = c["equity_money"].get("event")
    if isinstance(event, dict):
        event["position_share"]["probe"] = PROBE_SHARE_BEFORE
        event["max_open"]["probe"] = PROBE_OPEN_BEFORE
        event["one_share_max"].pop("probe", None)
    return c


def before_1019c(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of a constitution (the one in force when None) with RELEASE 1019c's row left out (`equity_money.event.
    max_orders_day`, `EVENT_ORDERS_ROW`) and A86's rows set back (`before_a86`): the table as release R2 left it
    (`DIGESTS_R2`; release 1019b's)."""
    c = before_a86(constitution)
    event = c["equity_money"].get("event")
    if isinstance(event, dict):
        event.pop(EVENT_ORDERS_ROW, None)
    return c


@contextmanager
def r2_back() -> Iterator[None]:
    """RELEASE R2'S ROWS SET BACK for the body, on the constitution in force (`before_r2`'s copy, in place): no
    `equity_money.event` block and `position_share.stock` at `STOCK_SHARE_BEFORE`. For a test of the old lanes' stop as
    it shipped (its digests, its grant), which R2 leaves as it was."""
    em = CONSTITUTION["equity_money"]
    with patch.dict(em["position_share"], {"stock": STOCK_SHARE_BEFORE}):
        event = em.pop("event", None)
        try:
            yield
        finally:
            if event is not None:
                em["event"] = event


def opens_on(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of a constitution (the one in force when None) with `equity_money.enabled` back at `ENABLED_BEFORE` and
    release R2's rows set back (`before_r2`): the table as it was from one open structure a Probe family (Oct 15,
    2026) until the old lanes' stop (`DIGESTS_OPENS_ON`). For the digest chain; the stop's rollback on the table as it
    stands is `stop_back`."""
    c = before_r2(constitution)
    c["equity_money"]["enabled"] = ENABLED_BEFORE
    return c


def stop_back(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of a constitution (the one in force when None) with THE OLD LANES' STOP ROLLED BACK ALONE: `equity_money.
    enabled` at `ENABLED_BEFORE`, every other row as it stands (release R2's event block and stock share kept). The
    machinery the stop leaves idle (a seat, a buy through the real book, a recorded week of orders) runs on it as it
    would the day the row is True again."""
    c = copy.deepcopy(dict(CONSTITUTION if constitution is None else constitution))
    c["equity_money"]["enabled"] = ENABLED_BEFORE
    return c


@contextmanager
def e1() -> Iterator[None]:
    """A20's DESIGN AS RELEASE E1 DEPLOYED IT for the body: three seats at 0.50, no seat block, and the opens on. E1's
    own digests are read here (7e41909a / e909eb10). The equity table cannot be built inside it (the block is a row of
    the table now): it is for a digest's pin alone."""
    with reference(), patch.dict(CONSTITUTION["options_money"]["probe"], {"open_per_family": OPF_BEFORE}), \
            patch.dict(CONSTITUTION["equity_money"], {"enabled": ENABLED_BEFORE}), \
            patch.dict(CONSTITUTION["equity_money"]["position_share"], {"stock": STOCK_SHARE_BEFORE}):
        probe = CONSTITUTION["equity_money"]["probe"]
        block = probe.pop("seat")
        panel = CONSTITUTION["equity_money"].pop("panel")
        event = CONSTITUTION["equity_money"].pop("event", None)
        try:
            yield
        finally:
            probe["seat"] = block
            CONSTITUTION["equity_money"]["panel"] = panel
            if event is not None:
                CONSTITUTION["equity_money"]["event"] = event


@contextmanager
def seat_rule(rule: str, **rows: Any) -> Iterator[None]:
    """The seat rule's block patched for the body: `rule` ("first-come" is the rollback) and any other of its rows."""
    with patch.dict(CONSTITUTION["equity_money"]["probe"]["seat"], {"rule": rule, **rows}):
        yield


# ------------------------------------------------------------------------------------------------ the rule, by hand
def walk(r: Rows, E: D, cash: D, asks: Sequence[tuple[str, str]], *, share: D = D("0.5"), price: D = D("100"),
         window_loss: D = ZERO, total_loss: D | None = None,
         held: Mapping[tuple[str, str], D] | None = None) -> list[tuple[D, str]]:
    """THE SIZING RULE WRITTEN OUT. `asks`: (program, ETF) in the order they are sized; each asks for `share` of its
    sleeve at `price` a share and is filled whole at it. `cash`: the account's cash before any lot. `window_loss`,
    `total_loss`: realized Probe losses already in the shared budget. `held`: lots already on the book ((program, ETF)
    -> dollars), bought with cash outside `cash`. [(dollars, the rule that set them)] in the asks' order.

    For each ask, in dollars:
      the sleeve          = sleeve x E
      the target          = share x the sleeve
      instrument room     = etf x E          - every program's holding of this ETF
      sleeve_cap room     = etf x the sleeve - this program's own holding of this ETF
      sleeve_cash room    = the sleeve       - everything this program holds
      invested room       = invested x E     - everything every program holds
      cash room           = the cash left    - the reserve
      budget room         = (the lower of window - window_loss and total - total_loss, less weight x everything held)
                            / weight
    The entry is the target unless a room is under it; then it is the smallest room, named by the first of the six, in
    that order, that is the smallest. Nothing or less: refused under that name. Else floored to whole millionths of a
    share at the price; under the minimum order after that: skipped ("min_order")."""
    lots: dict[tuple[str, str], D] = dict(held or {})
    spent = ZERO
    total_loss = window_loss if total_loss is None else total_loss
    out = []
    for program, symbol in asks:
        everything = sum(lots.values(), ZERO)
        sleeve = r.sleeve * E
        target = share * sleeve
        rooms = {
            "instrument": r.etf * E - sum((usd for (_, s), usd in lots.items() if s == symbol), ZERO),
            "sleeve_cap": r.etf * sleeve - lots.get((program, symbol), ZERO),
            "sleeve_cash": max(ZERO, sleeve - sum((usd for (p, _), usd in lots.items() if p == program), ZERO)),
            "invested": r.invested * E - everything,
            "cash": cash - spent - r.reserve,
            "budget": (min(r.window - window_loss, r.total - total_loss) - r.weight * everything) / r.weight,
        }
        usd, name = target, "intent"
        lowest = min(rooms.values())
        if lowest < target:
            usd, name = lowest, next(cap for cap in CAPS if rooms[cap] == lowest)
        if usd <= 0:
            out.append((ZERO, name))
            continue
        usd = (usd / price).quantize(QTY, rounding=ROUND_DOWN) * price
        if usd < r.min_order:
            out.append((ZERO, "min_order"))
            continue
        lots[(program, symbol)] = lots.get((program, symbol), ZERO) + usd
        spent += usd
        out.append((usd, name))
    return out


def figures(r: Rows, *, E: D = D("2000"), day_multiple: D = D(4)) -> dict[str, Any]:
    """THE CLOSED FORMS the documents state, as shares of E unless a name says dollars or a count:
    - `lot`: a one-ETF program's lot, the sleeve's own share of one ETF: sleeve x etf;
    - `seated`: a lot in every seat, as asked; `one_held`, `one_risk`: what the invested cap lets the lane hold of
      them (the lower of `seated` and the invested share), and its open risk at the ETF weight;
    - `same`, `rest`: how many programs hold a WHOLE lot of one ETF under the instrument cap (etf x E), and what the
      next program's lot of that ETF is;
    - `cash_fit`: how many of the seats' lots fit whole, each in its own ETF, when the account is all the capital
      (cash = E): under the invested cap and with the reserve left in cash;
    - `budget_fit`: how many fit whole in the window with nothing realized, at `E` dollars; `budget_e`: the largest
      whole-dollar E at which every seat's lot still fits the window;
    - `sleeves`, `held`, `held_risk`: whole sleeves asked for, what the invested cap lets the lane hold, its open risk;
    - `sends`, `ladder`, `ladders`: how many sends of one such lot the gateway's day line admits (`day_multiple` x
      equity of buys a day, a cancelled one too), the sends of the collar's whole ladder, and how many entries can
      each climb it."""
    lot = r.sleeve * r.etf
    seated = r.seats * lot
    same = int(r.etf // lot)
    sleeves = r.seats * r.sleeve
    held = min(sleeves, r.invested)
    ladder = r.max_bp // r.entry_bp
    sends = int(day_multiple // lot)
    return {
        "seats": r.seats, "sleeve": r.sleeve, "lot": lot, "seated": seated, "one_held": min(seated, r.invested),
        "one_risk": r.weight * min(seated, r.invested),
        "same": same, "rest": r.etf - same * lot,
        "cash_fit": min(r.seats, int(min(r.invested * E, E - r.reserve) // (lot * E))),
        "budget_fit": min(r.seats, int((r.window / r.weight) // (lot * E))),
        "budget_e": int(r.window / (r.weight * seated)),
        "sleeves": sleeves, "held": held, "held_risk": r.weight * held,
        "sends": sends, "ladder": ladder, "ladders": sends // ladder, "E": E, "day_multiple": day_multiple,
    }


# ------------------------------------------------------------------------------------- the House's own sizing function
class Lane:
    """An equity lane sized by THE REAL `size_entry` (league/equity/sizing.py) on the facts the book states to it
    (league/equity/live.py `EquityBook._size`): the sleeve is `probe.sleeve_share` x E (or the share passed), its free
    cash the sleeve less the program's own lots, the account's holding of the symbol every program's, the invested sum
    every lot, the available cash the account's cash less the reserve (`money.available_cash`), and the budget's room
    the lower of the window's and the total's less the open risk at the ETF weight (`EquityBook._budget_room`).
    Programs buy at their limit and are filled whole at it. `table`: a `league.live.money.Table` (the one in force, or
    a candidate's). `cash`: the account's cash before any lot. `held`: lots already on the book, as `walk`'s."""

    def __init__(self, table: Any, E: Any, cash: Any, *, window_loss: Any = "0", total_loss: Any = None,
                 held: Mapping[tuple[str, str], D] | None = None):
        self.table, self.eq = table, table.equity
        self.E, self.cash = D(str(E)), D(str(cash))
        self.window_loss = D(str(window_loss))
        self.total_loss = self.window_loss if total_loss is None else D(str(total_loss))
        self.lots: dict[tuple[str, str], D] = dict(held or {})
        self.spent = ZERO

    @property
    def invested(self) -> D:
        return sum(self.lots.values(), ZERO)

    def held(self, symbol: str) -> D:
        return sum((usd for (_, s), usd in self.lots.items() if s == symbol), ZERO)

    def own(self, program: str) -> D:
        return sum((usd for (p, _), usd in self.lots.items() if p == program), ZERO)

    def facts(self, program: str, symbol: str, *, share: Any = "0.5", limit: Any = "100.00",
              sleeve_share: D | None = None) -> Any:
        from league.equity.sizing import SizingInputs
        from league.live import money as M

        eq = self.eq
        weight = eq.open_risk_weight["etf"]
        sleeve = (eq.probe_sleeve_share if sleeve_share is None else sleeve_share) * self.E
        cash = self.cash - self.spent
        at_risk = weight * self.invested
        return SizingInputs(
            symbol=symbol, klass="etf", share=D(str(share)), usd=None, limit_price=D(str(limit)), E=self.E,
            sleeve_equity=sleeve, sleeve_free_cash=max(ZERO, sleeve - self.own(program)),
            sleeve_symbol_value=self.lots.get((program, symbol), ZERO), position_share=eq.position_share["etf"],
            account_symbol_value=self.held(symbol), invested_now=self.invested, invested_share=eq.invested_share,
            available_cash=M.available_cash({"cash": str(cash), "short_market_value": "0"}, working_buys_worst=ZERO,
                                            reserved=ZERO, reserve_usd=eq.cash_reserve),
            cash=cash, any_short=False,
            budget_room=min(self.table.probe_loss_budget - self.window_loss - at_risk,
                            self.table.probe_loss_total - self.total_loss - at_risk),
            weight=weight, min_order_usd=eq.min_order_usd)

    def buy(self, program: str, symbol: str, **kw: Any) -> Any:
        from league.equity.sizing import size_entry

        out = size_entry(self.facts(program, symbol, **kw))
        if out.usd > 0:
            self.lots[(program, symbol)] = self.lots.get((program, symbol), ZERO) + out.usd
            self.spent += out.usd
        return out


def table_at(seats: int, sleeve: str) -> Any:
    """The House's money table (`league.live.money.Table`) of a candidate's constitution WITH THE EQUITY OPENS ON
    (`stop_back`: the old lanes' stop's rollback, every other row as it stands). The tests that size, seat and buy
    through it drive the machinery the stop leaves idle, as it runs again, unchanged, the day `equity_money.enabled` is
    True again; what the stop itself does (no buy goes, every exit does) is held on the table in force in
    league/tests/test_equity_opens_off.py."""
    from league.live import money as M

    return M.Table.from_constitution(stop_back(constitution_at(seats, sleeve)))


@contextmanager
def opens() -> Iterator[None]:
    """THE EQUITY OPENS ON for the body: the constitution in force with `equity_money.enabled` at `ENABLED_BEFORE` (the
    old lanes' stop's rollback), nothing else moved, for a test of the machinery the stop leaves idle (a seat, a buy
    through the real book, a recorded week of orders) on the table in force (`Table.from_constitution()`)."""
    with patch.dict(CONSTITUTION["equity_money"], {"enabled": ENABLED_BEFORE}):
        yield


# ------------------------------------------------------------------------------------------------- the design blocks
def sh(value: D) -> str:
    """A share of E as the documents write it: at least two decimals, at most four, no trailing zero past two."""
    text = f"{D(value).quantize(D('0.0001'))}"
    while len(text.split(".")[1]) > 2 and text.endswith("0"):
        text = text[:-1]
    return text


def usd(value: Any) -> str:
    return f"${int(value):,}"


def gateway_day_multiple(repo: Path = REPO) -> D:
    """The gateway's STOCK_DAY_EQUITY_MULTIPLE (gateway/wrangler.jsonc, read as text: the var set once)."""
    [value] = re.findall(r'^\s*"STOCK_DAY_EQUITY_MULTIPLE"\s*:\s*"([^"]*)"', (repo / "gateway" / "wrangler.jsonc").read_text(),
                         flags=re.M)
    return D(value)


#: THE DESIGN BLOCK's sentences: the same words in every document; the slots are `figures` of the pair in force.
BODY = (
    "THE DESIGN IN FORCE: {seats} seats (`probe.max_programs`, `elane.roster`), a Probe sleeve of {sleeve} x E",
    "(`probe.sleeve_share`). A one-ETF program's lot is `position_share.etf` ({etf}) of its sleeve: {lot} x E.",
    "A lot in every seat asks for {seated} x E of ETFs; the lane holds at most {one_held} x E of them, {one_risk} x E of",
    "open risk at weight {weight}. One ETF across programs (the instrument cap, {etf} x E): {same} whole lots fit; the",
    "next program's lot of it is {rest} x E. At E = {E}, the account all cash and nothing realized: {cash_fit} of",
    "{seats} whole lots fit under the invested cap ({invested} x E) and the ${reserve} cash reserve alone, and",
    "{budget_fit} of {seats} in the ${window} window alone; the window alone holds all {seats} up to E = {budget_e}.",
    "Whole sleeves (programs that hold several ETFs) ask for {sleeves} x E; the lane holds at most {held} x E,",
    "{held_risk} x E of open risk. The options Probe lane keeps ${window} less the window's realized loss less {weight} x",
    "the equity lots: ${window} - {one_risk} x E against the one-ETF lots above. The gateway's day line ({day_multiple}x",
    "equity of buys a day, a cancelled one too) admits {sends} sends of such a lot: {ladders} entries can each climb the",
    "collar's ladder of {ladder} sends. A Sized sleeve (the step is parked) would be between {sleeve} x E and",
    "{sized} x E.",
)
#: The documents' line beside the block's: the digests of the pair in force (never in the constitution's own comment).
DIGEST_LINE = ("Money digest `{money}`, full digest `{full}` (`PINNED_DIGEST`); the rollback, `set_design 3 0.50`, is "
               "`{back_money}` / `{back_full}`.")
#: Where each block lives: (path, the line that opens it, the line that closes it, each line's prefix).
BLOCKS: dict[str, tuple[str, str, str, str]] = {
    "constitution": ("league/constitution.py", "    # <equity-design>", "    # </equity-design>", "    #   "),
    "operations": ("docs/operations.md", "<!-- equity-design:begin -->", "<!-- equity-design:end -->", ""),
    "interfaces": ("league/equity/INTERFACES.md", "<!-- equity-design:begin -->", "<!-- equity-design:end -->", ""),
    "changelog": ("CHANGELOG.md", "<!-- equity-design:begin -->", "<!-- equity-design:end -->", ""),
}


def slots(constitution: Mapping[str, Any] | None = None, *, repo: Path = REPO) -> dict[str, str]:
    """Every slot of `BODY` and `DIGEST_LINE` as text, from a constitution's rows (the one in force when None)."""
    c = CONSTITUTION if constitution is None else constitution
    r = rows_of(c)
    f = figures(r, day_multiple=gateway_day_multiple(repo))
    back = copy.deepcopy(dict(c))
    back["equity_money"]["probe"].update(max_programs=REFERENCE[0], sleeve_share=REFERENCE[1])
    return {
        "seats": str(f["seats"]), "sleeve": sh(f["sleeve"]), "etf": sh(r.etf), "lot": sh(f["lot"]),
        "seated": sh(f["seated"]), "one_held": sh(f["one_held"]), "one_risk": sh(f["one_risk"]),
        "weight": sh(r.weight), "same": str(f["same"]),
        "rest": sh(f["rest"]), "invested": sh(r.invested), "reserve": f"{r.reserve:f}", "cash_fit": str(f["cash_fit"]),
        "window": f"{r.window:f}", "budget_fit": str(f["budget_fit"]), "E": usd(f["E"]), "budget_e": usd(f["budget_e"]),
        "sleeves": sh(f["sleeves"]), "held": sh(f["held"]), "held_risk": sh(f["held_risk"]),
        "day_multiple": f"{f['day_multiple']:f}", "sends": str(f["sends"]), "ladders": str(f["ladders"]),
        "ladder": str(f["ladder"]), "sized": sh(r.sized),
        "money": money_digest(dict(c))[:8], "full": digest(dict(c))[:8],
        "back_money": money_digest(back)[:8], "back_full": digest(back)[:8],
    }


def block(kind: str, constitution: Mapping[str, Any] | None = None, *, repo: Path = REPO) -> list[str]:
    """THE DESIGN BLOCK of document `kind` (`BLOCKS`) as its lines, between (not with) the lines that open and close
    it: `BODY` filled from the constitution's rows, each line under the document's prefix; the digests' line after it
    in every document but the constitution itself."""
    prefix = BLOCKS[kind][3]
    values = slots(constitution, repo=repo)
    lines = [prefix + line.format(**values) for line in BODY]
    if kind != "constitution":
        lines.append(prefix + DIGEST_LINE.format(**values))
    return lines


def read_block(kind: str, *, repo: Path = REPO) -> list[str]:
    """The lines a document holds between its block's opening and closing lines (each exactly once in the file)."""
    path, begin, end, _ = BLOCKS[kind]
    lines = (repo / path).read_text(encoding="utf-8").split("\n")
    if lines.count(begin) != 1 or lines.count(end) != 1 or lines.index(begin) > lines.index(end):
        raise ValueError(f"{path}: the design block's lines ({begin!r}, {end!r}) are each there once, in order")
    return lines[lines.index(begin) + 1:lines.index(end)]


def write_block(kind: str, constitution: Mapping[str, Any] | None = None, *, repo: Path = REPO) -> bool:
    """Write document `kind`'s block from the constitution's rows; True when the file changed. (`set_design`'s.)"""
    path, begin, end, _ = BLOCKS[kind]
    file = repo / path
    text = file.read_text(encoding="utf-8")
    lines = text.split("\n")
    read_block(kind, repo=repo)
    a, b = lines.index(begin), lines.index(end)
    new = "\n".join(lines[:a + 1] + block(kind, constitution, repo=repo) + lines[b:])
    if new == text:
        return False
    file.write_text(new, encoding="utf-8")
    return True


__all__ = ["SEATS", "SLEEVES", "CANDIDATES", "REFERENCE", "DIGESTS", "DIGESTS_E5S", "Rows", "rows_of", "in_force",
           "DIGESTS_E5A", "DIGESTS_E4S2", "OPF_BEFORE", "before_opf1", "DIGESTS_OPENS_ON", "ENABLED_BEFORE", "opens_on", "opens",
           "DIGESTS_STOP", "STOCK_SHARE_BEFORE", "before_r2", "r2_back", "stop_back", "DIGESTS_R2", "EVENT_ORDERS_ROW",
           "before_1019c", "DIGESTS_1019C", "PROBE_SHARE_BEFORE", "PROBE_OPEN_BEFORE", "A86_ROLLBACK", "before_a86",
           "DIGESTS_A86", "REACH_BAR_ROW", "S2_ROLLBACK", "S2_OFF", "before_1019h", "DIGESTS_1019H", "V6_SLOTS_ROW",
           "ROLLBACK_1019I", "S2_OFF_1019I", "V6_SLOTS_OFF", "before_1019i", "V3_ROWS_BEFORE", "before_1019l",
           "DIGESTS_1019I", "DIGESTS_1019L", "V8_SLOTS_ROW", "V8_SLOTS_OFF", "ROLLBACK_1019N", "before_1019n",
           "constitution_at", "design", "reference", "without_seat", "without_panel", "e1", "seat_rule", "walk", "figures", "Lane", "table_at", "sh", "usd", "gateway_day_multiple", "BODY",
           "DIGEST_LINE", "BLOCKS", "slots", "block", "read_block", "write_block"]
