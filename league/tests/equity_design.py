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
  which each pair still has with that row set back (`opens_on`); every older table's helper sets it back too.
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
#: <r2-digests>
#: Each candidate's (money digest, full digest), pinned, WITH THE SEAT RULE'S BLOCK, THE PANEL ROW, ONE OPEN STRUCTURE A
#: PROBE FAMILY, THE OLD LANES' STOP AND RELEASE R2 AS THEY STAND (the event lane's real money, `equity_money.event`;
#: `position_share.stock` 0.10: the owner's goal of Oct 19, 2026, item 4, and PREREG-EVL-1 section 8): the grant
#: re-ratifies on the first, `PINNED_DIGEST` is the second. They moved once, with R2, from `DIGESTS_STOP`; they were
#: regenerated by the tree's own functions (`money_digest` and `digest` of `constitution_at` each pair, what
#: `set_design` checks a pair against), and `set_design` at a pair lands on its pin here.
DIGESTS: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("e421fef90ed217fcba406fd355e7cd19ba29545a5c2836b17d65e6415ee94641",
                  "81d73cd8f4c1432c716302e6c49ebcf1193559e7814653b5f7f427f1c22e435f"),
    (3, "0.33"): ("26e8eaf06505e905682d9316c114eb04408043a153d0227478f325b788c3e772",
                  "12b8a254d1ab4c76ff1a8c2040eb239b35661c4a43dba88216439292a2d7d47e"),
    (3, "0.25"): ("9a5dcc8e0a2c4a6bb1f8869bb6e141cb9d399ee6e388cfef73eda693e2a6eda3",
                  "591480b0aec3392f066bc6b1d00c0794c6b1f61f66f7c4f8e49ef77ce120fb62"),
    (4, "0.50"): ("1830e595329d6e1357aa4453a92e003817868170b207ca4e7afab7f8c61c9c2e",
                  "7901ed586da4681245ee3e0eb81b05e1c6b3dff9f1d4c7c9644e44770417d3bc"),
    (4, "0.33"): ("b200c1b496353cd3bc0f0668780c190e701d83ed5021af2ea57c8e90a8f53da5",
                  "a212831022104d1cefd0ba4a6b7a02744f3aae073409d3b7f5c6a630d7dee72a"),
    (4, "0.25"): ("d5210a70a800d5d3d430cc208ba1bd97f9320fd07efd9a4066053175b3c602b5",
                  "6f9fb62b20218967d20c8ca262e0e08c93f339cd6264f700e5d8e74c936f4148"),
    (5, "0.50"): ("bcbe4635ef4062763caef9f9084f98e0864b51fbbae6dbcb322fd807ee611a54",
                  "72816e8848caa88f7539db9f1fb3372852b142e50f4a317e7bc2c900b32e088f"),
    (5, "0.33"): ("6fa6746b475b410ccf4e41a61136871adb899d57cbbe7cf946cee7be408011f7",
                  "ee7cca37dcb6e5688478ce4d6ec039ba145cd70c78ff957357fb66dd8f19c38c"),
    (5, "0.25"): ("e9c9a112a7405e6e55bcbc9d4cc8fb7288eefe29cb7f1934ed68550a75a69820",
                  "c3db19de009391a76242109f0b94406564f0cef0349a8210bd507dc24603ac97"),
    (6, "0.50"): ("59301b702fae651682b771184ef75b72d708f16ecf9c877f4c5f05f1d3d1f989",
                  "fdda4ec96d76b06c37833f63fe274b30a49a3fbf2493cdf1e94c2e285b5e80dc"),
    (6, "0.33"): ("60ccca14f8ed8a1a1baa57edffb6ceb4310c1226164d0aa3e844f4729e185d64",
                  "8a682c7d0041357d0291af2b4cf66c3f58ed8caeb2b3d3b392cb4960745721b1"),
    (6, "0.25"): ("1142ae87b9535db060db8624f97501459ee8b316925c1255c98d17c0d58c9c52",
                  "bd1ff4f69e1dc189f92879b8ace1d20fd2c399871344996db37c8a6579ec0ce9"),
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
           "DIGESTS_STOP", "STOCK_SHARE_BEFORE", "before_r2", "r2_back", "stop_back",
           "constitution_at", "design", "reference", "without_seat", "without_panel", "e1", "seat_rule", "walk", "figures", "Lane", "table_at", "sh", "usd", "gateway_day_multiple", "BODY",
           "DIGEST_LINE", "BLOCKS", "slots", "block", "read_block", "write_block"]
