# PROJECT CHECKPOINT

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | PROJECT-CHECKPOINT |
| Purpose | Repository-authoritative checkpoint for the latest frozen milestone and next authorized work |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Checkpoint content baseline (HEAD this content was authored against) | `fc5e8659d5a35b609c96a689b8b250f7f869d73d` (`chore: freeze MILESTONE-028 Application Query/QueryHandler Contracts implementation`, pushed) |
| Checkpoint content baseline origin/master | `fc5e8659d5a35b609c96a689b8b250f7f869d73d` (identical — pushed) |

This document is updated at each milestone freeze or major checkpoint. It supersedes its own prior content; it does not rewrite any frozen milestone document.

**On self-reference:** the values in this table and in the `CHECKPOINT_CONTENT_BASELINE_*` fields below describe the repository state this checkpoint content was authored against. They are not a live, self-updating record of Git HEAD. A document cannot cite the hash of the commit that first contains it without creating a recursive follow-up-commit cycle. To find live repository truth, run `git rev-parse HEAD` and `git status --short --branch` directly.

## 2. Current State

```text
LATEST_FROZEN_MILESTONE=MILESTONE-056
MACRO_MILESTONE_PROTOCOL_ACTIVE_FROM=MILESTONE-036
CHECKPOINT_CONTENT_BASELINE_BRANCH=master
CHECKPOINT_CONTENT_BASELINE_HEAD=fc5e8659d5a35b609c96a689b8b250f7f869d73d
CHECKPOINT_CONTENT_BASELINE_ORIGIN=fc5e8659d5a35b609c96a689b8b250f7f869d73d
CHECKPOINT_CONTENT_BASELINE_STATUS=PUSHED_UP_TO_DATE_AT_M028_IMPLEMENTATION_FREEZE_M029_SCOPE_SELECTED

M020_STATUS=APPROVED_AND_FROZEN
M020_DESIGN_COMMIT=fd96b70366a7bbed2172a8f51d7d7cc52b60bc41
M020_IMPLEMENTATION_COMMIT=e20bc76d2dc0be359cea2c385c210e081fb48a35
M020_CORRECTION_COMMIT=efed86be608471fdaa2956f7827fc9236209763a
M020_FREEZE_COMMIT=40dd6b6a0c02e710e3f7efe84e8959af51f839f9

M021_STATUS=APPROVED_AND_FROZEN
M021_DESIGN_COMMIT=06d22defd6f06b96d0a46c5e91bc169e55e674e5
M021_DESIGN_FREEZE_COMMIT=abeba5a1407a8d31ce6d07fe3e071804d2385457
M021_IMPLEMENTATION_COMMIT=73ffd3647bce749dff5c8f228f90f3be79413a9c
M021_IMPLEMENTATION_FREEZE_COMMIT=fdb180a2b21776cf37fe36826741a54ef7b43ad4

M022_STATUS=APPROVED_AND_FROZEN
M022_DESIGN_COMMIT=ccd1077a733915e4a345001e505e25bee33696a9
M022_DESIGN_CORRECTION_COMMIT=1179e307782549401157cf2b251276614fe10fa2
M022_DESIGN_FREEZE_COMMIT=4ce351d6d933c9199310337add4490cafcca4d20
M022_IMPLEMENTATION_COMMIT=69920125214b577485096406b9a2b2b573bead81
M022_IMPLEMENTATION_CORRECTION_COMMIT=c7d75334ae9f7fd760e67135eb90248f1747f1b5
M022_IMPLEMENTATION_FREEZE_COMMIT=10425e85b63a0b6f18b73b962355f22176cb279c

M023_STATUS=APPROVED_AND_FROZEN
M023_DESIGN_COMMIT=a6e1350b8c37467d3a33b73c6e254c34ce4aab1b
M023_DESIGN_CORRECTION_COMMITS=7dcc7c10e247163d6e029fb6520fd76846e328d6,0f5c982a23f1b8c51ed5d56ff0a0cdab0c03c4bb,7933b567129e525ec4cf6235de3f22e3d737860f
M023_DESIGN_FREEZE_COMMIT=cb6ff16788b2ad8a26ed9f82a903d276daa6d3c4
M023_IMPLEMENTATION_COMMIT=4a93e44ea937885d45f5ce6587c2b963452ac8ff
M023_EVIDENCE_CORRECTION_COMMITS=f3f7fc097db37470dc731009176e065df1d5a70b,c6fb2c9d7f153d1b3fbee97a7b647d7ecca6d5af,5679034cf2f3887f7329cf56c5c73c1865208451
M023_IMPLEMENTATION_FREEZE_COMMIT=4ce800d3609ba7c621eadffc338bc5bc2503228d

M024_STATUS=APPROVED_AND_FROZEN
M024_SCOPE=Multi-Aggregate Persistence Unit of Work
M024_DESIGN_COMMIT=f2a22817cb433142960dba6509c50b4b39066ebe
M024_DESIGN_CORRECTION_COMMIT=03d640fa8e0f34fb3348226c4bc0eeaa386832b4
M024_DESIGN_FREEZE_COMMIT=ed0a4198dab515c4d204f3046ea2cfc114390bef
M024_IMPLEMENTATION_COMMIT=5fd00247bdb25b01a4f5de831b5b9baa483af6a5
M024_IMPLEMENTATION_CORRECTION_COMMIT=9f8bb60507f52ee410f1fd3010ad11641884f329
M024_IMPLEMENTATION_FREEZE_COMMIT=b2283281f670703c95de0b6fe8ee83d58c5e3ac1

M025_SCOPE=Repository Runtime Composition
M025_DESIGN_COMMIT=e9db9292982f3795cc51c29de290af2e34e1b33b
M025_DESIGN_CORRECTION_COMMIT=ec6e8db23dddf20ae8ab2efec17908dc61a69be4
M025_DESIGN_FREEZE_COMMIT=fe4f04483cb5fdc6b5cf08e0fe0eeebbe4e827ad
M025_IMPLEMENTATION_COMMIT=907eb9c0f6ca04f0b5c660c8bcf1da09e3deeb9b
M025_TRUTH_CORRECTION_COMMIT=956f4f85c5e08d76c7f1a54aa1a6ff8b40645fc8
M025_IMPLEMENTATION_FREEZE_COMMIT=0d57c36adf8b60ea3be9e86fa3814d1e2b459253
M025_STATUS=APPROVED_AND_FROZEN

M026_SCOPE=Foundation Runtime Repository Composition
M026_DESIGN_COMMIT=110bdab25a7867798ec1d14faba816f22738a7d2
M026_DESIGN_CORRECTION_COMMIT=1664c8e17cedac80715b9eb82ffff14620423191
M026_DESIGN_FREEZE_COMMIT=bb434cd19a21cf25571ab14326cfdbd536de441c
M026_IMPLEMENTATION_COMMIT=c6802c5d3f3b295368fa36d8d50cd26ecca8f460
M026_IMPLEMENTATION_FREEZE_COMMIT=45f4916d1fcdd76b28fffa81c23704f6b0355c3d
M026_STATUS=APPROVED_AND_FROZEN

M027_SCOPE=Application Command/Handler Contracts
M027_DESIGN_COMMIT=2b914ffdf4425d7d6904caaa681d39142d73ba7e
M027_DESIGN_CORRECTION_COMMIT=7753b135bb324a7c1337c542d87660a855c3ee0f
M027_DESIGN_FREEZE_COMMIT=64abc16156b949491ded4ff239d2c249aac569a8
M027_DESIGN_STATUS=APPROVED_AND_FROZEN
M027_IMPLEMENTATION_COMMIT=c7bc632a1568203f33635191ea70b4e5784e1d86
M027_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M027_IMPLEMENTATION_APPROVAL=APPROVED
M027_IMPLEMENTATION_FREEZE=FROZEN
M027_STATUS=APPROVED_AND_FROZEN

M028_SCOPE=Application Query/QueryHandler Contracts
M028_DESIGN_COMMIT=db99194277aecef7b5a5c74f576a940d6e24e399
M028_DESIGN_CORRECTION_COMMIT=bff0865f7f2495b1854a86d04c0db66ecb0512b1
M028_DESIGN_FREEZE_COMMIT=e062d14ef80feb3df4f4862c3e117fb930b41c01
M028_DESIGN_STATUS=APPROVED_AND_FROZEN
M028_IMPLEMENTATION_COMMIT=a71de466c707f5665f6826f0fcb35f1aee90181c
M028_IMPLEMENTATION_CORRECTION_COMMIT=8d3069a464ba58d53b51e687d142a7e42474e7af
M028_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M028_IMPLEMENTATION_APPROVAL=APPROVED
M028_IMPLEMENTATION_FREEZE=FROZEN
M028_STATUS=APPROVED_AND_FROZEN

M029_SCOPE=Application Service Orchestration
M029_SCOPE_SELECTION_COMMIT=449d7ef3005402e4c92052fc8720dbd19b623102
M029_SCOPE_SELECTION_STATUS=SCOPE_SELECTED_READY_FOR_RE_REVIEW
M029_SCOPE_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M029_SCOPE_STATUS=APPROVED_AND_FROZEN
M029_SCOPE_FREEZE_STATUS=APPROVED_AND_FROZEN
M029_SCOPE_FREEZE_COMMIT=22cec98d4bd724e00754551034b896236989acec
M029_DESIGN_STATUS=APPROVED_AND_FROZEN
M029_DESIGN_COMMIT=f047d3a33fcd8ba4849a5be1f75abc74c64a362f
M029_DESIGN_FREEZE_COMMIT=81650aeb58e073134127062e8451de6d241f7c5e
M029_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M029_IMPLEMENTATION_COMMIT=5b8a7d8a7e6bcd3852161c8fe0fafff5c7f5f986
M029_IMPLEMENTATION_HASH_RECORDING_COMMIT=231584e1bb95cd24f88f86691703564bbe6237de
M029_EVIDENCE_GOVERNANCE_CORRECTION_COMMIT=a2a64d6bbf166b1d0ef63cbdbb4a6842d50f7ba5
M029_IMPLEMENTATION_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M029_IMPLEMENTATION_FREEZE_COMMIT=8a076c69314e5ea0fba5835fc1c9d165c7498a2c
M029_STATUS=APPROVED_AND_FROZEN

M030_SCOPE=Concrete Application Command Vertical Slice (Campaign Creation)
M030_SCOPE_STATUS=APPROVED_AND_FROZEN
M030_SCOPE_COMMIT=2b4ac748304d3859b78b6a1900849fab7b6fec35
M030_SCOPE_REVIEW_STATUS=APPROVED_FOR_OWNER_FREEZE
M030_SCOPE_FREEZE_STATUS=APPROVED_AND_FROZEN
M030_SCOPE_FREEZE_COMMIT=52f07c03195926e4f3a67dc1524aba7c206a09cb
M030_DESIGN_STATUS=APPROVED_AND_FROZEN
M030_DESIGN_COMMIT=6c12c77fdded4d42caaba1f37287dabf2c5c577a
M030_DESIGN_CORRECTION_COMMIT=b0dba94927c8067f0d55aa6790bcf71bb82cb0a6
M030_DESIGN_REVIEW_STATUS=APPROVED_FOR_OWNER_FREEZE
M030_DESIGN_FREEZE_STATUS=APPROVED_AND_FROZEN
M030_DESIGN_FREEZE_COMMIT=990ce7c82a531015b883f7a2d3f8889107e6eee9
M030_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M030_IMPLEMENTATION_COMMIT=bb66826225f621368ea317b5757631bf94731a56
M030_IMPLEMENTATION_REVIEW_STATUS=APPROVED_FOR_OWNER_FREEZE
M030_IMPLEMENTATION_FREEZE_STATUS=APPROVED_AND_FROZEN
M030_IMPLEMENTATION_FREEZE_COMMIT=64682d1790ed3efacbdbdb6d99b3f3b4e7bbee90
M030_STATUS=APPROVED_AND_FROZEN

M031_SCOPE=Concrete Application Query Vertical Slice (Campaign Retrieval)
M031_SCOPE_STATUS=APPROVED_AND_FROZEN
M031_SCOPE_COMMIT=68bd50d1d2e2d38abb3e3e389e4a8dde6d996848
M031_SCOPE_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M031_SCOPE_FREEZE_STATUS=APPROVED_AND_FROZEN
M031_SCOPE_FREEZE_COMMIT=b31b664e9395aa0a988ccd1aecc21d6b06436d39
M031_DESIGN_STATUS=APPROVED_AND_FROZEN
M031_DESIGN_COMMIT=f73b924d3c36e4796087aa4bb889a8dcde7b548e
M031_DESIGN_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M031_DESIGN_FREEZE_STATUS=APPROVED_AND_FROZEN
M031_DESIGN_FREEZE_COMMIT=196150dcde88610c9bc78e6bd0ff40d4d5da9d9b
M031_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M031_IMPLEMENTATION_COMMIT=840310c880f4645ab9a1c9e8219d09b4408f9845
M031_IMPLEMENTATION_FINALIZATION_COMMIT=fb4b52ce521756168f74b660e7846114630b8622
M031_IMPLEMENTATION_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M031_IMPLEMENTATION_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M031_IMPLEMENTATION_FREEZE_COMMIT=f144c963f6bcf90a8ada5cf14853fce5e73d48d8
M031_STATUS=APPROVED_AND_FROZEN

M032_SCOPE=Concrete Application Command Vertical Slice (Campaign Lifecycle Transition)
M032_SCOPE_STATUS=APPROVED_AND_FROZEN
M032_SCOPE_COMMIT=5ea62d02d65945f0976e42b8c011217d895723e4
M032_SCOPE_REVIEW_STATUS=APPROVED_FOR_OWNER_SCOPE_FREEZE
M032_SCOPE_FREEZE_STATUS=APPROVED_AND_FROZEN
M032_SCOPE_FREEZE_COMMIT=b18878a514694d6663026e11d98859023c04a136
M032_DESIGN_STATUS=APPROVED_AND_FROZEN
M032_DESIGN_COMMIT=50f2cd829af2e10799ab3581b4c2e56e9e04d401
M032_DESIGN_CORRECTION_COMMIT=2f48b1e4af1b039c3b2a7e3598f85e63e007b216
M032_DESIGN_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M032_DESIGN_FREEZE_STATUS=APPROVED_AND_FROZEN
M032_DESIGN_FREEZE_COMMIT=14204e4c24024fa7e1d56fbf49dccef0a1fa6a58
M032_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M032_IMPLEMENTATION_COMMIT=2901a6e7f6c305a86a8ba7635a436c9299433519
M032_FINALIZATION_COMMIT=8db4febca15299861103c26f716d19b3a5d5bd29
M032_IMPLEMENTATION_REVIEW_STATUS=APPROVED_FOR_OWNER_FREEZE
M032_IMPLEMENTATION_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M032_IMPLEMENTATION_FREEZE_COMMIT=84fcf35082aafc1a02358f2e3aa8f7de81841cc9
M032_STATUS=APPROVED_AND_FROZEN

M033_SCOPE=Concrete Application Command Vertical Slice (Run Creation)
M033_SCOPE_STATUS=APPROVED_AND_FROZEN
M033_SCOPE_COMMIT=04e274240f7958d80bc0cb87f92f825b563fbd5a
M033_SCOPE_FREEZE_STATUS=APPROVED_AND_FROZEN
M033_SCOPE_FREEZE_COMMIT=44dd29e34f6150bd37bc466eed14098d75ac57ab
M033_DESIGN_STATUS=APPROVED_AND_FROZEN
M033_DESIGN_COMMIT=8edead3bc25d786cef8563f4fc4815a889a3a447
M033_DESIGN_FREEZE_STATUS=APPROVED_AND_FROZEN
M033_DESIGN_FREEZE_COMMIT=ec802143626e850dafe70ce9f0f561fa8516df94
M033_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M033_IMPLEMENTATION_COMMIT=59fb2ffaa244886990bf68da018c138777a209f0
M033_FINALIZATION_COMMIT=244864dc7339862ae7f4593a48c8280c4d9d27a0
M033_EVIDENCE_CORRECTION_COMMIT=18dabb8966a0b54572aea684e4a5075448052bc0
M033_IMPLEMENTATION_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M033_IMPLEMENTATION_FREEZE_COMMIT=38ed45518d8a2068d29e7375c2c09ea2af80963c
M033_STATUS=APPROVED_AND_FROZEN

M034_SCOPE=Concrete Application Query Vertical Slice (Run Retrieval)
M034_SCOPE_STATUS=APPROVED_AND_FROZEN
M034_SCOPE_COMMIT=3ee8485143f1397cad9d14bc55744e97f60aa9d3
M034_SCOPE_CORRECTION_COMMIT=60178d3d1caf96d1fe33f318e57e94c708e8896f
M034_SCOPE_FREEZE_STATUS=APPROVED_AND_FROZEN
M034_SCOPE_FREEZE_COMMIT=e6ad2c0e976ad0eb1cd00f8e15544d58ac45de7e
M034_DESIGN_STATUS=APPROVED_AND_FROZEN
M034_DESIGN_COMMIT=d343e38cba9b5a49db278c72ca1650dd50839bd2
M034_DESIGN_CORRECTION_COMMIT=993144e4361372e6978b11d96d6e1fe98e722c73
M034_DESIGN_FREEZE_STATUS=APPROVED_AND_FROZEN
M034_DESIGN_FREEZE_COMMIT=072fcee1d75c3f13547a6033c689786f2a110ab3
M034_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M034_IMPLEMENTATION_COMMIT=aef1ee96cf9662e6b726bdb1168fe3d79bc8a79e
M034_FINALIZATION_COMMIT=7196a3b4a8b67eaa1745b87b67dca98212e8935f
M034_IMPLEMENTATION_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M034_IMPLEMENTATION_FREEZE_COMMIT=3056e3010b4f20f3cf7bf2ab2e3fbbc43fcff825
M034_STATUS=APPROVED_AND_FROZEN

M035_SCOPE=Concrete Application Command Vertical Slice (Run Lifecycle Transition)
M035_SCOPE_STATUS=APPROVED_AND_FROZEN
M035_SCOPE_COMMIT=26aab1acb1d08150144b8ce52d63f17796f121ef
M035_SCOPE_FREEZE_STATUS=APPROVED_AND_FROZEN
M035_SCOPE_FREEZE_COMMIT=cebbd945107f4242cada86eea29e210e7b7c701c
M035_DESIGN_STATUS=APPROVED_AND_FROZEN
M035_DESIGN_COMMIT=bac7f202c4f6dca591702d4d1404a8390c4bb755
M035_DESIGN_FREEZE_STATUS=APPROVED_AND_FROZEN
M035_DESIGN_FREEZE_COMMIT=3227bba3d22756bc138cd45bbb0ac98824bc537c
M035_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M035_IMPLEMENTATION_COMMIT=1037876fac376238298c22cfae0b4d5b949ffaac
M035_FINALIZATION_COMMIT=1b42d8ac943175eb4e4c2fc064062054854dedd7
M035_IMPLEMENTATION_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M035_IMPLEMENTATION_FREEZE_COMMIT=6853d988634ae264d6e625a90b9ba6815d908df5
M035_STATUS=APPROVED_AND_FROZEN
M036_SCOPE=Concrete Application Command Vertical Slice (EvidencePackage Creation)
M036_SCOPE_STATUS=APPROVED_AND_FROZEN
M036_DESIGN_STATUS=APPROVED_AND_FROZEN
M036_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M036_IMPLEMENTATION_COMMIT=4672cfc7137e19aa628ebe996883e10a1d3f90c3
M036_FINALIZATION_COMMIT=cd5083289008b2735281f53ab45a2c90a90b0f51
M036_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M036_IMPLEMENTATION_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M036_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M036_OWNER_FREEZE_COMMIT=8c5f04cb2e4b32749fc6ba04806b33ac38c0216f
M036_STATUS=APPROVED_AND_FROZEN
M037_SCOPE=Concrete Application Query Vertical Slice (EvidencePackage Retrieval)
M037_SCOPE_STATUS=APPROVED_AND_FROZEN
M037_DESIGN_STATUS=APPROVED_AND_FROZEN
M037_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M037_IMPLEMENTATION_COMMIT=d041d94492f678f049ae48dfb5edd4ded1f76c39
M037_FINALIZATION_COMMIT=10ea710f9c010e093774d02e6c05717cf3a873e2
M037_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M037_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M037_OWNER_FREEZE_COMMIT=9c53e1de89093bc12244ccb50ce2ced11947f396
M037_STATUS=APPROVED_AND_FROZEN

M038_SCOPE=Concrete Application Command Vertical Slice (EvidencePackage Collection Start)
M038_SCOPE_STATUS=APPROVED_AND_FROZEN
M038_DESIGN_STATUS=APPROVED_AND_FROZEN
M038_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M038_IMPLEMENTATION_COMMIT=a77ef2fd8abd17244f80698cbb7b6ea972c06a0d
M038_FINALIZATION_COMMIT=56d35586368124998c47c164b07a583f8dce716a
M038_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M038_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M038_OWNER_FREEZE_COMMIT=cf3907a30ddbea6609be8ba322ff3f3c7cfb6bd7
M038_STATUS=APPROVED_AND_FROZEN

M039_SCOPE=Concrete Application Command Vertical Slice (EvidencePackage Criterion-Result Recording)
M039_SCOPE_STATUS=APPROVED_AND_FROZEN
M039_DESIGN_STATUS=APPROVED_AND_FROZEN
M039_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M039_IMPLEMENTATION_COMMIT=9ec849a04bb76d11f391988979c4d9fce54e3beb
M039_FINALIZATION_COMMIT=adf0ec7a26b3aeda5e7f98d1e4ecdb2deed0405e
M039_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M039_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M039_OWNER_FREEZE_COMMIT=e7c1ae10bea6eada60a6ed4aa39cffa2b902bf6c
M039_STATUS=APPROVED_AND_FROZEN

M040_SCOPE=Concrete Application Command Vertical Slice (EvidencePackage Artifact-Reference Recording)
M040_SCOPE_STATUS=APPROVED_AND_FROZEN
M040_DESIGN_STATUS=APPROVED_AND_FROZEN
M040_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M040_IMPLEMENTATION_COMMIT=912bfea8179d762281fab5c79aa93975792177d9
M040_FINALIZATION_COMMIT=a0f0f14713c7243911061467cdb25516d4a467f2
M040_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M040_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M040_OWNER_FREEZE_COMMIT=62dd6595ce6d039f67c25ebc891b1cd4efab1e73
M040_STATUS=APPROVED_AND_FROZEN

M041_SCOPE=Concrete Application Command Vertical Slice (EvidencePackage Sealing)
M041_SCOPE_STATUS=APPROVED_AND_FROZEN
M041_DESIGN_STATUS=APPROVED_AND_FROZEN
M041_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M041_IMPLEMENTATION_COMMIT=7f332e7006e8fe452bac1bc62b23fb73fdb7f963
M041_FINALIZATION_COMMIT=4db6fa4417ffe62ae055f60b40d8ad0dadbd4f9c
M041_DESIGN_CORRECTION_STATUS=COMPLETED
M041_DESIGN_CORRECTION_COMMIT=556b21263182eed229b6528b37c4fa2c4d1e69d6
M041_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M041_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M041_OWNER_FREEZE_COMMIT=22cd0afdb84c9a789f380b67db72614b8231bd39
M041_STATUS=APPROVED_AND_FROZEN

M042_SCOPE=Concrete Application Command Vertical Slice (Review Creation)
M042_SCOPE_STATUS=APPROVED_AND_FROZEN
M042_DESIGN_STATUS=APPROVED_AND_FROZEN
M042_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M042_IMPLEMENTATION_COMMIT=4614c73f0807f9c1db29c51039ce33b254a69d71
M042_FINALIZATION_COMMIT=01c0cbacf75989442aa1289321c5990c6d3235eb
M042_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M042_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M042_OWNER_FREEZE_COMMIT=e915c8cb647c4fc7f7a4fc4ad18585ec42199da1
M042_STATUS=APPROVED_AND_FROZEN

M043_SCOPE=Concrete Application Query Vertical Slice (Review Retrieval)
M043_SCOPE_STATUS=APPROVED_AND_FROZEN
M043_DESIGN_STATUS=APPROVED_AND_FROZEN
M043_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M043_IMPLEMENTATION_COMMIT=c29404f93aff217073de20718f5bed5567000855
M043_FINALIZATION_COMMIT=d43ad9a3c4afed2ab405209385fcdb5170f694e1
M043_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M043_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M043_OWNER_FREEZE_COMMIT=4b9770cd2dd80fa1b1968871f08167c07f8fddca
M043_STATUS=APPROVED_AND_FROZEN

M044_SCOPE=Concrete Application Command Vertical Slice (Review Lifecycle Transition)
M044_SCOPE_STATUS=APPROVED_AND_FROZEN
M044_DESIGN_STATUS=APPROVED_AND_FROZEN
M044_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M044_IMPLEMENTATION_COMMIT=37733f357bcabb864a0a0576bba4621685d35621
M044_FINALIZATION_COMMIT=e64414222d6ec45342612fb9788750430fa85c27
M044_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M044_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M044_OWNER_FREEZE_COMMIT=ce45ba7b17ec8fb90a0751b465fadfa9043c1c46
M044_STATUS=APPROVED_AND_FROZEN

M045_SCOPE=Concrete Application Command Vertical Slice (Review Finding Recording)
M045_SCOPE_STATUS=APPROVED_AND_FROZEN
M045_DESIGN_STATUS=APPROVED_AND_FROZEN
M045_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M045_IMPLEMENTATION_COMMIT=4b02842f0fe784e8c9f217582a4a323286725300
M045_FINALIZATION_COMMIT=3a63ddbbe0c3edfebc4e3ccf319884fcf9c0270a
M045_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M045_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M045_OWNER_FREEZE_COMMIT=426412db74034314b90091365accf5de35ed4ed4
M045_STATUS=APPROVED_AND_FROZEN

M046_SCOPE=Concrete Application Command Vertical Slice (Review Completion)
M046_SCOPE_STATUS=APPROVED_AND_FROZEN
M046_DESIGN_STATUS=APPROVED_AND_FROZEN
M046_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M046_IMPLEMENTATION_COMMIT=147c12a20b3be62e31bc272c06383f88c1c3845f
M046_FINALIZATION_COMMIT=6da3675b3df4b6187ac0be8c6daa2f4eb785515f
M046_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M046_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M046_OWNER_FREEZE_COMMIT=7c390db264989edfffda8c8d4cf4ed0bde7245ac
M046_STATUS=APPROVED_AND_FROZEN

M047_SCOPE=Concrete Application Command Vertical Slice (Campaign Cancellation)
M047_SCOPE_STATUS=APPROVED_AND_FROZEN
M047_DESIGN_STATUS=APPROVED_AND_FROZEN
M047_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M047_IMPLEMENTATION_COMMIT=1f35acaf042dc04f650378126ecdc4fc4f509321
M047_FINALIZATION_COMMIT=297719266500582a841462be9f934feb378aa9d1
M047_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M047_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M047_OWNER_FREEZE_COMMIT=53e3c4786922ea82e5d85ba5ce59dbfeb9dad934
M047_STATUS=APPROVED_AND_FROZEN

M048_SCOPE=Concrete Application Command Vertical Slice (Run Execution Failure)
M048_SCOPE_STATUS=APPROVED_AND_FROZEN
M048_DESIGN_STATUS=APPROVED_AND_FROZEN
M048_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M048_IMPLEMENTATION_COMMIT=c78099fdd0638a252de94ce3f21cc1512ccdfea6
M048_FINALIZATION_COMMIT=cc1526dde697e453c9498ecc26a663251589c0ad
M048_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M048_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M048_OWNER_FREEZE_COMMIT=de71d3521bdf0e13159ff155544ee034aa8ea8aa
M048_STATUS=APPROVED_AND_FROZEN

M049_SCOPE=Concrete Application Command Vertical Slice (Review Cancellation)
M049_SCOPE_STATUS=APPROVED_AND_FROZEN
M049_DESIGN_STATUS=APPROVED_AND_FROZEN
M049_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M049_IMPLEMENTATION_COMMIT=c0c649d551744c57a3696296ab0a73b5a9696146
M049_FINALIZATION_COMMIT=c2c0380472a10f6e7489c80d0b9cb1b8e8462493
M049_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M049_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M049_OWNER_FREEZE_COMMIT=3ae497c32dd93579409f6a156391196ce910ec82
M049_STATUS=APPROVED_AND_FROZEN

M050_SCOPE=Application Composition Root (Real End-to-End Campaign Retrieval)
M050_SCOPE_STATUS=APPROVED_AND_FROZEN
M050_DESIGN_STATUS=APPROVED_AND_FROZEN
M050_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M050_IMPLEMENTATION_COMMIT=e5d65385f01b6617657bc86d24426f6dec8babf2
M050_FINALIZATION_COMMIT=9a1331c9c1d7e3c362fa835f9856e8a5ea1150d1
M050_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M050_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M050_OWNER_FREEZE_COMMIT=77f7ed85c58493d144349dd8c41f8e15000d2b8c
M050_STATUS=APPROVED_AND_FROZEN

M051_SCOPE=Application Composition Root (Real End-to-End Campaign Cancellation)
M051_SCOPE_STATUS=APPROVED_AND_FROZEN
M051_DESIGN_STATUS=APPROVED_AND_FROZEN
M051_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M051_IMPLEMENTATION_COMMIT=06f42a7f153545a5669253b847199f680c0cad31
M051_FINALIZATION_COMMIT=bc173721e71474727f0ba44a7b5ec18ff9a38627
M051_MACRO_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M051_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M051_OWNER_FREEZE_COMMIT=b69a95b18ed9879c9443a97317bc866d563f53b9
M051_STATUS=APPROVED_AND_FROZEN

M052_SCOPE=Application Composition Root (Real End-to-End Campaign Creation)
M052_SCOPE_STATUS=APPROVED_AND_FROZEN
M052_DESIGN_STATUS=APPROVED_AND_FROZEN
M052_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M052_IMPLEMENTATION_COMMIT=59173e21bf040aa4560bd30ff7792225cd8a774e
M052_FINALIZATION_COMMIT=f17e6d3ddcffdedb680c21a439a615f837d78742
M052_MACRO_REVIEW_STATUS=APPROVED_ZERO_FINDINGS
M052_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M052_OWNER_FREEZE_COMMIT=c98928470c58baac48f0dfb51018cb63c1d6f957
M052_STATUS=APPROVED_AND_FROZEN

M053_SCOPE=Evidence Submission Workflow (Run + EvidencePackage Composition Roots)
M053_SCOPE_STATUS=APPROVED_AND_FROZEN
M053_DESIGN_STATUS=APPROVED_AND_FROZEN
M053_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M053_IMPLEMENTATION_COMMIT=531ea1daa1816d6d7eb7d24b3e1cfdd15d992123
M053_MACRO_REVIEW_STATUS=APPROVED_ZERO_FINDINGS
M053_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M053_OWNER_FREEZE_COMMIT=3b49475f630c67ad44cc0ee00d24868e91445839
M053_STATUS=APPROVED_AND_FROZEN

M054_SCOPE=Review Workflow Production Composition
M054_SCOPE_STATUS=APPROVED_AND_FROZEN
M054_DESIGN_STATUS=APPROVED_AND_FROZEN
M054_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M054_IMPLEMENTATION_COMMIT=87985fc338471e3c65de67b2c9eb81745e8597a3
M054_MACRO_REVIEW_STATUS=APPROVED_ZERO_FINDINGS
M054_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M054_OWNER_FREEZE_COMMIT=bdea032e0d12e33a97008cac088ee9d9087f73cd
M054_STATUS=APPROVED_AND_FROZEN

M055_SCOPE=Run Execution Lifecycle End-to-End
M055_SCOPE_STATUS=APPROVED_AND_FROZEN
M055_DESIGN_STATUS=APPROVED_AND_FROZEN
M055_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M055_IMPLEMENTATION_COMMIT=6da49c3d694da28405977f59f8d52e2899b2fdc8
M055_MACRO_REVIEW_STATUS=APPROVED_ZERO_FINDINGS
M055_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M055_OWNER_FREEZE_COMMIT=9c5b574d7edf9454c8e1b5c5f7d6fd4b8bf618e4
M055_STATUS=APPROVED_AND_FROZEN

M056_SCOPE=Campaign Lifecycle End-to-End
M056_SCOPE_STATUS=APPROVED_AND_FROZEN
M056_DESIGN_STATUS=APPROVED_AND_FROZEN
M056_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M056_IMPLEMENTATION_COMMIT=9191857335ec2372cd85d66caf6f283430256f0
M056_MACRO_REVIEW_STATUS=APPROVED_ZERO_FINDINGS
M056_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M056_OWNER_FREEZE_COMMIT=6656dfa6cdf229ae46a1fb5907dbbec15afeae16
M056_STATUS=APPROVED_AND_FROZEN
M056_CORE_ENGINE_CLOSURE=CAMPAIGN_RUN_EVIDENCEPACKAGE_REVIEW_SEQUENTIALLY_COMPOSABLE

M057_STATUS=NOT_STARTED
NEXT_PERMITTED_ACTION=MILESTONE-057 (RECOMMENDATION: TRADING-PRODUCT INTEGRATION, NOT FURTHER AGGREGATE-COMPLETENESS WORK -- SEE M056 FINAL REPORT)
```

## 3. Frozen Milestone Summary

M020 froze persistence-neutral domain repository and optimistic-concurrency contracts for Campaign, Run, EvidencePackage, and Review.

M021 froze mapper contracts and durable-record shapes for the same four aggregates.

M022 froze the PostgreSQL schema and Alembic migration that persist those durable records.

M023 froze concrete PostgreSQL mappers and repository adapters implementing M020/M021 over M022.

M024 froze the low-level multi-aggregate persistence Unit of Work primitive, exposed only as `PostgresPersistenceService.run_composed(operations)`, allowing multiple repository operations that share one `PostgresPersistenceService` to commit or roll back atomically without changing repository Protocols or concrete repository adapter source files.

M025 froze the repository runtime composition boundary, `PostgresRepositoryRuntime`, composing the four M023 repository adapters over one shared, caller-owned `PostgresPersistenceService` and delegating cross-repository atomic execution to the frozen M024 `run_composed` primitive, with eager one-time construction, `is`-stable property identity, mandatory constructor validation, no readiness probe, and independent-root support governed by the existing M024 same-service-identity rule.

M026 froze the extension of the existing `FoundationRuntime` process-startup composition root with a `repository_runtime: PostgresRepositoryRuntime | None` field, constructed inside `initialize_infrastructure_runtime` and `initialize_foundation_runtime_with_postgresql` only when the persistence service in use is a real `PostgresPersistenceService` (an `isinstance` guard that leaves the field `None` for every `FakePersistenceService`-based caller, preserving all pre-existing bootstrap test behavior unmodified), with the identical same-service-identity, no-second-cleanup-entry, and repr/credential-safety discipline M025 already established. **Post-freeze correction:** a resource-lifecycle defect of the same class as M050-Y-1 — `initialize_foundation_runtime_with_postgresql` and `initialize_foundation_runtime_with_object_storage` never closed their constructed service when its own `.initialize()` raised — was identified during MILESTONE-052 exploratory review, independently reproduced, and corrected without any scope, design, or public-contract change; see `MILESTONE_026_FOUNDATION_RUNTIME_REPOSITORY_COMPOSITION_IMPLEMENTATION.md` Section 17. `M026_STATUS` remains `APPROVED_AND_FROZEN`.

M027 froze the persistence-neutral, domain-agnostic `CommandHandler[_CommandT_contra, _ResultT_co]` Protocol in `shared/contracts/command.py` — the application-layer command/write-side vocabulary — with verified contravariant/covariant generics, a mypy-checked positive conformance proof, and an isolated, empirically verified negative type-check fixture mechanism kept outside the canonical `mypy` gate. No concrete command, handler, orchestration, dispatcher, registry, or error hierarchy was introduced.

M028 froze the persistence-neutral, domain-agnostic `QueryHandler[_QueryT_contra, _QueryResultT_co]` Protocol in `shared/contracts/query.py` — the application-layer query/read-side counterpart to M027's `CommandHandler` — with the identical verified contravariant/covariant generics pattern, a mypy-checked positive conformance proof, the identical negative type-check fixture mechanism, and an explicit frozen distinction between the two contracts' declared relationship (no inheritance, shared base, alias, or cross-import) and Python's structural-typing reality (a single concrete class may satisfy both Protocols simultaneously when types align, which this design does not attempt to prevent). Read-side intent is semantic only; no mechanical read-only enforcement exists. No concrete query, handler, orchestration, dispatcher, registry, cache, pagination wrapper, or error hierarchy was introduced.

## 4. MILESTONE-024 Closure Evidence

M024 implementation freeze commit: `b2283281f670703c95de0b6fe8ee83d58c5e3ac1`.

Fresh freeze validation:

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `scripts/verify.ps1` | PASS - `366 passed, 96 skipped`, coverage `82.15%` |
| `scripts/security.ps1` | PASS - pip-audit clean, secret scan 255 targets |
| Ruff format/check | PASS |
| mypy | PASS - 79 source files |
| Architecture checker | PASS |
| Build | PASS - sdist and wheel built |
| Disposable PostgreSQL regression | PASS - `87 passed` across M022/M023/M024 integration suites |

M024 does not authorize repository runtime composition, application services, retry policy, APIs, workers, Audit runtime, Decision Candidate, Decision Freeze, market-data behavior, vendor behavior, trading behavior, or any empirical campaign execution.

## 5. MILESTONE-025 Closure Evidence

M025 implementation freeze commit: `0d57c36adf8b60ea3be9e86fa3814d1e2b459253`.

Authority chain: design `e9db9292982f3795cc51c29de290af2e34e1b33b` → design correction `ec6e8db23dddf20ae8ab2efec17908dc61a69be4` → design freeze `fe4f04483cb5fdc6b5cf08e0fe0eeebbe4e827ad` → implementation `907eb9c0f6ca04f0b5c660c8bcf1da09e3deeb9b` → truth correction `956f4f85c5e08d76c7f1a54aa1a6ff8b40645fc8` → implementation freeze `0d57c36adf8b60ea3be9e86fa3814d1e2b459253`. Repository evidence after M024 identified the scope as **Repository Runtime Composition** (M024 Design Section 21 explicitly deferred "Candidate E, repository runtime composition"; M024 Implementation Freeze Section 7 explicitly did not authorize it).

Independent review found one MAJOR finding at the design stage (repeated-access identity and eager-vs-lazy construction were undefined; corrected in the design-correction commit) and one MAJOR governance-truth finding at the implementation stage (`PROJECT_CHECKPOINT.md` and the external review package described the implementation as uncommitted after the implementation commit already existed; corrected in the truth-correction commit, verified byte-for-byte consistent across all governance artifacts on final re-review). No functional, architectural, PostgreSQL, test, or security defect was found at any stage.

Fresh freeze validation:

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `scripts/verify.ps1` | PASS - `389 passed, 105 skipped`, coverage `82.60%` |
| `scripts/security.ps1` | PASS - pip-audit clean, secret scan 264 targets |
| Ruff format/check | PASS |
| mypy | PASS - 80 source files |
| Architecture checker | PASS |
| Build | PASS - sdist and wheel built |
| Disposable PostgreSQL regression | PASS - `96 passed` across M022/M023/M024/M025 integration suites |
| External review package | PASS - `complete.diff` byte-identical to Git, 28/28 manifest hashes verified, ZIP SHA-256 `5785fd5bb4e1f9e8a0aec7952e9a08fd940f68cc88da409ba12c807c671c9fb9` |

M025 does not authorize application services, retry policy, APIs, workers, Audit runtime, Decision Candidate, Decision Freeze, market-data behavior, vendor behavior, trading behavior, or any empirical campaign execution, or any MILESTONE-026 implementation.

## 6. MILESTONE-026 Closure Evidence

M026 implementation freeze commit: `45f4916d1fcdd76b28fffa81c23704f6b0355c3d`.

Authority chain: design `110bdab25a7867798ec1d14faba816f22738a7d2` → design correction `1664c8e17cedac80715b9eb82ffff14620423191` → design freeze `bb434cd19a21cf25571ab14326cfdbd536de441c` → implementation `c6802c5d3f3b295368fa36d8d50cd26ecca8f460` → implementation freeze `45f4916d1fcdd76b28fffa81c23704f6b0355c3d`. Repository evidence after M025 identified the scope as **Foundation Runtime Repository Composition** (the one process-startup composition root, `FoundationRuntime`, had no way to obtain a `PostgresRepositoryRuntime`, and the existing bootstrap test suite revealed the `FakePersistenceService`-compatibility constraint the design had to resolve).

Independent review found exactly two MINOR documentation-completeness findings at the design stage (repr/credential-safety rule and test obligation; post-construction failure and cleanup semantics — both corrected in the design-correction commit) and no finding at all at the implementation stage. No functional, architectural, PostgreSQL, test, or security defect was found at any stage.

Fresh freeze validation:

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `scripts/verify.ps1` | PASS - `406 passed, 110 skipped`, coverage `82.70%` |
| `scripts/security.ps1` | PASS - pip-audit clean, secret scan 271-272 targets |
| Ruff format/check | PASS |
| mypy | PASS - 80 source files |
| Architecture checker | PASS |
| Build | PASS - sdist and wheel built |
| Disposable PostgreSQL regression | PASS - `101 passed` across M022/M023/M024/M025/M026 integration suites |
| External review package | PASS - `complete.diff` byte-identical to Git, 29/29 manifest hashes verified, ZIP SHA-256 `5be251764869a1a2069ee46148d0b0e650517b0f5c53b6fe29c2f769e169ee9a` |

M026 does not authorize application services, retry policy, APIs, workers, Audit runtime, Decision Candidate, Decision Freeze, market-data behavior, vendor behavior, trading behavior, or any empirical campaign execution, or any MILESTONE-027 implementation.

## 7. MILESTONE-027 Closure Evidence

Authority chain: design `2b914ffdf4425d7d6904caaa681d39142d73ba7e` → design correction `7753b135bb324a7c1337c542d87660a855c3ee0f` → design freeze `64abc16156b949491ded4ff239d2c249aac569a8` → implementation `c7bc632a1568203f33635191ea70b4e5784e1d86` → implementation freeze recorded via `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_IMPLEMENTATION_FREEZE.md` (this checkpoint update is bundled into that same freeze commit; see that document for the exact freeze commit's own hash, which this content cannot self-cite without a recursive cycle — see Section 1's self-reference note). Repository evidence after M026 identified the scope as **Application Command/Handler Contracts** (no `Command`/`Handler` type existed anywhere in the codebase; M020's repository-Protocol precedent was the direct model for freezing a contract before any concrete implementation).

Independent review found two MAJOR findings at the design stage (generic variance was invariant rather than contravariant/covariant — an actual `mypy`-rejected Protocol definition, verified by direct experimentation; the negative type-check strategy for proving malformed handlers rejected was undefined) and one MINOR finding (stale Scope Selection wording describing rejected components as selected) — all corrected in the design-correction commit. Independent review of the implementation found zero CRITICAL, zero MAJOR, and zero blocking MINOR findings; no correction commit was required.

Fresh freeze validation:

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `scripts/verify.ps1` | PASS - `416 passed, 110 skipped`, coverage `82.73%` |
| `scripts/security.ps1` | PASS - pip-audit clean, secret scan 288 targets |
| Ruff format/check | PASS |
| mypy | PASS - 81 source files |
| Architecture checker | PASS |
| Build | PASS - sdist and wheel built |
| External review package | PASS - `complete.diff` byte-identical to Git, 31/31 manifest hashes verified, ZIP SHA-256 `0b87d30525690ef22dba1d9eaef9d956ddeb8cf305c5dee27519a984c4bb64b0` |

M027 does not authorize any concrete `Command`/`CommandHandler` implementation, a handler-level error hierarchy, a `Command` marker, a dispatcher/registry, application service orchestration, retry policy, APIs, workers, Audit runtime, Decision Candidate, Decision Freeze, market-data/vendor/trading/campaign execution behavior, or any MILESTONE-028 implementation start on its own authority.

## 8. MILESTONE-028 Closure Evidence

Authority chain: design `db99194277aecef7b5a5c74f576a940d6e24e399` → design correction `bff0865f7f2495b1854a86d04c0db66ecb0512b1` → design freeze `e062d14ef80feb3df4f4862c3e117fb930b41c01` → implementation `a71de466c707f5665f6826f0fcb35f1aee90181c` → narrow checkpoint correction `8d3069a464ba58d53b51e687d142a7e42474e7af` (removed one duplicated `M029_STATUS=NOT_STARTED` line from this document's own prior Section 2, discovered during repository-truth verification; no source, test, or fixture file touched) → implementation freeze recorded via `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_IMPLEMENTATION_FREEZE.md` (this checkpoint update is bundled into that same freeze commit; see that document for the exact freeze commit's own hash, which this content cannot self-cite without a recursive cycle — see Section 1's self-reference note). Repository evidence after M027 identified the scope as **Application Query/QueryHandler Contracts** — the CQRS read-side counterpart to M027's `CommandHandler`.

Independent review found one MAJOR finding at the design stage (structural interchangeability with `CommandHandler` was overstated as "no type relationship" when Python's structural typing allows one concrete class to satisfy both Protocols simultaneously when types align) and one MINOR finding (read-only semantics described without stating clearly that it is not mechanically enforced) — both corrected in the design-correction commit. Independent review of the implementation found zero CRITICAL, zero MAJOR, and zero blocking MINOR findings; no implementation correction commit was required. The narrow checkpoint correction (`8d3069a`) is a documentation-only truth fix discovered during freeze-mission repository-truth verification, not an implementation defect.

Fresh freeze validation:

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `scripts/verify.ps1` | PASS - `438 passed, 110 skipped`, coverage `82.77%` |
| `scripts/security.ps1` | PASS - pip-audit clean, secret scan 302 targets |
| Ruff format/check | PASS - 176 files formatted |
| mypy | PASS - 82 source files |
| Architecture checker | PASS |
| Build | PASS - sdist and wheel built |
| External review package | PASS - `complete.diff` byte-identical to Git, 40/40 manifest hashes verified, ZIP SHA-256 `7a619efc5b447051012587a2683be5bae620b714ce9632e43f6870480e487f73` |

M028 does not authorize any concrete `Query`/`QueryHandler` implementation, a declared relationship/shared base/unification with `CommandHandler`, a query-level error hierarchy, a `Query` marker, a dispatcher/registry, caching, pagination, read-only transaction enforcement, application service orchestration, retry policy, APIs, workers, Audit runtime, Decision Candidate, Decision Freeze, market-data/vendor/trading/campaign execution behavior, or any MILESTONE-029 work.

## 9. Deferred Capabilities

- retry-on-`OptimisticConcurrencyConflict` policy (evidence base remains a single concrete conflict-producing command — see the M033 scope document Section 22);
- any Run lifecycle-transition command (deferred by MILESTONE-034's own scope — see the M034 scope document Sections 14, 21-22; a real future candidate once Run's read side is proven);
- any additional Campaign lifecycle-transition command beyond the one MILESTONE-032 targets;
- any command or query for `EvidencePackage` or `Review`;
- any composition-root abstraction beyond direct binding, pending evidence of genuine repeated-handler need;
- APIs, workers, Audit runtime, Decision Candidate, Decision Freeze;
- market-data, vendor, trading, or empirical campaign execution behavior.

## 10. Next Authorized Work

MILESTONE-027 is `APPROVED_AND_FROZEN` at both the design and implementation stages (Section 7). MILESTONE-028 is `APPROVED_AND_FROZEN` at both the design and implementation stages (Section 8): the corrected design (Version 1.1) was frozen via `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_DESIGN_FREEZE.md`; the implementation, reviewed with zero CRITICAL, zero MAJOR, and zero blocking MINOR findings, was frozen via `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_IMPLEMENTATION_FREEZE.md`. MILESTONE-029 is `APPROVED_AND_FROZEN` at the scope stage (Section 11; scope-freeze commit `22cec98d4bd724e00754551034b896236989acec`), at the design stage (design commit `f047d3a33fcd8ba4849a5be1f75abc74c64a362f`, frozen via `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_DESIGN_FREEZE.md`), and at the implementation stage (implementation commit `5b8a7d8a7e6bcd3852161c8fe0fafff5c7f5f986`, owner-frozen via `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_IMPLEMENTATION_FREEZE.md` after a final independent implementation re-review found all previously blocking evidence/governance findings resolved). MILESTONE-029 is fully `APPROVED_AND_FROZEN` at every stage (Section 12). MILESTONE-030 scope — Concrete Application Command Vertical Slice (Campaign Creation) — is `APPROVED_AND_FROZEN` (Section 13; scope commit `2b4ac748304d3859b78b6a1900849fab7b6fec35`) after a hostile independent scope review found exactly one architectural capability with no hidden design, implementation, sequencing, or governance defect. MILESTONE-030 has a design candidate — answering all ten required architectural questions (command/handler package placement, dependency injection, entry-point binding, identity supply, validation ownership, repository interaction sequence, error propagation, and the one justified architecture-checker change) — recorded in `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_DESIGN.md` (Section 14). A hostile independent design review found two MAJOR defects in the architecture-checker decision (a claim that `usecases` needed `shared.persistence` access, contradicting the handler's own Protocol-only dependency design, and a missing `FORBIDDEN_IMPORT_PREFIXES["usecases"]` entry required to actually enforce that Protocol-only boundary) and one MINOR governance defect in this document. All three were corrected: the design states the precise dependency model (`CampaignRepository` + `RuntimeIdentifierGenerator` Protocols only, no persistence import anywhere in `usecases`), specifies the required paired `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` checker change, and this document's narrative was realigned. A final independent design delta re-review then independently re-derived and verified the underlying technical claims against the actual `tools/check_architecture.py` source (not merely the design's own assertions) and confirmed no other decision was reopened, concluding: **M030 DESIGN APPROVED FOR OWNER FREEZE.** The owner formally froze the design via `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_DESIGN_FREEZE.md`. MILESTONE-030 implemented exactly `CreateCampaignCommand`/`CreateCampaignHandler` in `empirical_platform.usecases.create_campaign`, the paired `ALLOWED["usecases"]`/`FORBIDDEN_IMPORT_PREFIXES["usecases"]` architecture-checker addition, and focused unit/contract/integration/architecture-fixture tests (implementation commit `bb66826225f621368ea317b5757631bf94731a56`). A hostile independent implementation review verified the change scope, prohibited-pattern absence, and test rigor directly against the real commit (not the implementation's own claims), independently reproduced the real-PostgreSQL evidence from a completely fresh Docker container twice, and concluded: **M030 IMPLEMENTATION APPROVED FOR OWNER FREEZE.** The owner formally froze the implementation via `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_IMPLEMENTATION_FREEZE.md`. MILESTONE-030 is now `APPROVED_AND_FROZEN` at every stage — scope, design, and implementation (Section 15). MILESTONE-031 scope — Concrete Application Query Vertical Slice (Campaign Retrieval) — is `APPROVED_AND_FROZEN` (Section 16; scope commit `68bd50d1d2e2d38abb3e3e389e4a8dde6d996848`) after a hostile independent scope review found exactly one coherent read-side capability with no hidden design, implementation, sequencing, or governance defect (two non-blocking governance observations were raised and resolved in this same freeze). MILESTONE-031 design — resolving all ten open design questions the scope freeze deferred (query shape, handler placement, repository dependency, return shape, repository interaction, not-found behavior, validation ownership, `QueryEntryPoint` binding, architecture-checker impact, PostgreSQL evidence strategy), recorded in `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_DESIGN.md` (design candidate commit `f73b924d3c36e4796087aa4bb889a8dcde7b548e`) — is `APPROVED_AND_FROZEN` (Section 17) after a hostile independent design review found zero CRITICAL and zero MAJOR findings (three non-blocking MINOR findings were raised and resolved in the freeze record). MILESTONE-031 implemented exactly `GetCampaignQuery`/`GetCampaignHandler`/`CampaignSnapshot` in `empirical_platform.usecases.get_campaign`, with zero `tools/check_architecture.py` change and 22 new focused unit/contract/integration tests (implementation document `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_IMPLEMENTATION.md`). A hostile independent implementation review verified the change scope, prohibited-pattern absence, and test rigor directly against the real commits (not the implementation's own claims), independently reproduced the real-PostgreSQL evidence from a completely fresh Docker container twice, independently re-verified the external review package's manifest and ZIP from a fresh extraction, and concluded: **M031 IMPLEMENTATION APPROVED WITH NON-BLOCKING OBSERVATIONS** (two narrative-accuracy-only findings — a miscounted test total and a stale secret-scan target count — corrected in this same freeze; no CRITICAL or MAJOR finding). The owner formally froze the implementation via `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_IMPLEMENTATION_FREEZE.md`. MILESTONE-031 is now `APPROVED_AND_FROZEN` at every stage — scope, design, and implementation (Section 18). MILESTONE-032 scope — Concrete Application Command Vertical Slice (Campaign Lifecycle Transition) — is `APPROVED_AND_FROZEN` (Section 19; scope candidate commit `5ea62d02d65945f0976e42b8c011217d895723e4`) after an architectural-inventory-driven gap analysis found that `CampaignRepository.save()` and its `OptimisticConcurrencyConflict` contract, frozen since M020/M023, have never been exercised by any application-layer command — the literal next dependency both M030's and M031's own frozen text explicitly named (independently re-verified by direct repository search during review, not merely asserted). A hostile independent scope review confirmed the gap, the candidate comparison, scope purity, and frozen-contract preservation, and found three non-blocking documentation findings — two fabricated-quotation citations of M030/M031 predecessor text and one internal 7-vs-8-method terminology inconsistency — all corrected in this same freeze without reopening the underlying selection. Decision: **APPROVED FOR OWNER SCOPE FREEZE.** The owner formally froze the scope via `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_SCOPE_FREEZE.md`. MILESTONE-032 now has a design candidate (Section 19) — a systematic 8-candidate mutation analysis selected `Campaign.prepare_for_authorization()` (the literal first lifecycle transition, reachable directly from the `DRAFT` state M030 already produces), a caller-supplied `expected_persisted_version` model (the only option that keeps the `OptimisticConcurrencyConflict` path honestly testable without an unauthorized interleaving hook), and a `SaveResult` return contract (unlike M031's read-side reasoning, a write-side caller genuinely needs the new persisted version) — recorded in `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_DESIGN.md`. A hostile independent design review verified every load-bearing decision against actual frozen source and found the design's PostgreSQL conflict scenario relied on an inaccurate citation of M023's own conflict test and, as originally written, would not actually reach `OptimisticConcurrencyConflict` — concluding **M032 DESIGN REQUIRES CORRECTION** (one MAJOR finding, M032-DESIGN-REVIEW-0001; every other decision independently verified sound). A narrow correction pass resolved the finding by specifying `Campaign.revise_scope_statement()`, performed through an independently loaded aggregate, as the interfering write, with an explicit explanation of why `prepare_for_authorization()` cannot serve that role. A final independent design re-review confirmed the corrected mechanism is genuine and deterministic, that no other decision was disturbed, and that no second application capability was introduced, raising one further non-blocking observation (residual "directly mirrors M023" wording elsewhere in the document, resolved in this same freeze without altering any architectural decision) — concluding **M032 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS.** The owner formally froze the design via `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_DESIGN_FREEZE.md`. MILESTONE-032 implemented exactly `PrepareCampaignForAuthorizationCommand`/`PrepareCampaignForAuthorizationHandler` in `empirical_platform.usecases.prepare_campaign_for_authorization`, with zero `tools/check_architecture.py` change and 25 new focused unit/contract/integration tests (implementation document `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_IMPLEMENTATION.md`). A hostile independent implementation review verified the change scope, prohibited-pattern absence, and test rigor directly against the real commits (not the implementation's own claims), independently reproduced the real-PostgreSQL success, deterministic-conflict, and invalid-transition evidence from a fresh Docker container — confirming the frozen `OptimisticConcurrencyConflict` mechanism (`revise_scope_statement()` as the interfering write) genuinely works exactly as the corrected design specifies — independently re-verified the external review package's manifest and ZIP from a fresh extraction, and concluded: **M032 IMPLEMENTATION APPROVED FOR OWNER FREEZE** (no CRITICAL or MAJOR finding, no correction required). The owner formally froze the implementation via `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_IMPLEMENTATION_FREEZE.md`. MILESTONE-032 is now `APPROVED_AND_FROZEN` at every stage — scope, design, and implementation (Section 21). MILESTONE-033 scope — Concrete Application Command Vertical Slice (Run Creation) — is `APPROVED_AND_FROZEN` (Section 22; scope candidate commit `04e274240f7958d80bc0cb87f92f825b563fbd5a`) after an architectural-inventory-driven comparative analysis found Campaign's application-layer proof structurally complete (create/read/update all proven across M030-M032) while `Run`/`EvidencePackage`/`Review` remain completely unproven at the application layer, and selected `Run` creation over `EvidencePackage`/`Review` creation, a fourth Campaign-only command, the retry policy, composition-root wiring, transport, and audit/registry work, using an explicit nine-criterion comparison matrix with evidence-based rejection reasons for every alternative (scope document Sections 6-8). A hostile independent scope review found no CRITICAL, MAJOR, or blocking MINOR finding and concluded **M033 SCOPE APPROVED FOR OWNER FREEZE.** The owner formally froze the scope via `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_SCOPE_FREEZE.md`. MILESTONE-033 design — selecting persistence-enforced Campaign-existence validation (no application-level `CampaignRepository` lookup, relying on the real `run.campaign_id → campaign.governance_id` foreign-key constraint verified directly in the M022 migration), a caller-supplied-governance/handler-generated-runtime identity model mirroring M030, a `DomainIdentity[RunId]` return contract, and exactly one narrow architecture-checker addition (`"run"` to `ALLOWED["usecases"]`) — recorded in `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_DESIGN.md` (design candidate commit `8edead3bc25d786cef8563f4fc4815a889a3a447`) — is `APPROVED_AND_FROZEN` (Section 23) after a hostile independent design review found zero CRITICAL, zero MAJOR, and zero blocking MINOR findings (one non-blocking observation on the intentional missing-Campaign `FoundationError` exposure was preserved, not corrected). Decision: **M033 DESIGN APPROVED FOR OWNER FREEZE.** The owner formally froze the design via `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_DESIGN_FREEZE.md`. MILESTONE-033 implemented exactly `CreateRunCommand`/`CreateRunHandler` in `empirical_platform.usecases.create_run`, with the one narrow `ALLOWED["usecases"]` addition the design freeze authorized and 23 new focused unit/contract/integration tests (implementation document `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_IMPLEMENTATION.md`). An initial hostile independent implementation review found the implementation itself sound but the external-review package untrustworthy (stale `complete.diff`/`repository-truth.txt`, incorrect test and secret-scan counts); a narrow evidence-only correction (commit `18dabb8966a0b54572aea684e4a5075448052bc0`) resolved all four findings without touching any production source, test, checker, or frozen authority. A final independent re-review concluded **M033 IMPLEMENTATION APPROVED FOR OWNER FREEZE.** The owner formally froze the implementation via `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_IMPLEMENTATION_FREEZE.md`. MILESTONE-033 is now `APPROVED_AND_FROZEN` at every stage — scope, design, and implementation (Section 24). MILESTONE-034 scope — Concrete Application Query Vertical Slice (Run Retrieval) — is `APPROVED_AND_FROZEN` (Section 25; scope candidate commit `3ee8485143f1397cad9d14bc55744e97f60aa9d3`) after a fresh, from-source architectural-inventory rebuild found that `CommandHandler`/`CommandEntryPoint` generalization to a second aggregate is now proven (M033, via `Run` creation), while `QueryHandler`/`QueryEntryPoint` generalization remains completely unproven for any aggregate beyond `Campaign` — `GetCampaignHandler` (M031) is still the only concrete query handler that has ever existed. `Run` retrieval was selected over a Run lifecycle-transition command (a harder, write-side generalization question, and a departure from this project's established create→read→update sequencing for one aggregate) and over `EvidencePackage` creation (which would repeat an already-twice-proven `add()` pattern rather than close an open architectural question), using an explicit comparison matrix (scope document Sections 6-8). A hostile independent scope review found one MAJOR/BLOCKING finding (`M034-SCOPE-REVIEW-0001`): the scope prematurely committed the retrieval result to a "read value"/"immutable, milestone-local read value" shape in Sections 9 and 13, a design decision that must not be frozen at scope selection. A narrow correction (commit `60178d3d1caf96d1fe33f318e57e94c708e8896f`) removed every such commitment, replacing it with neutral language — the handler returns one retrieval result, exact type/representation resolved during the Design Mission — without reopening the selected capability or any other scope decision. A final independent scope re-review found no corrections remaining and concluded **M034 SCOPE APPROVED FOR OWNER FREEZE.** The owner formally froze the scope via `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_SCOPE_FREEZE.md`. MILESTONE-034 now has a design candidate (Section 26) — selecting `GetRunQuery` carrying full `DomainIdentity[RunId]`, and, as the central load-bearing decision, a new milestone-local `RunSnapshot` (`identity`/`campaign_id`/`state`, no `persisted_version`) over the raw `Run` aggregate (mutability leakage) or `LoadedAggregate[Run]` (mutability plus persisted-version leakage), with `manifests`/`transition_history` independently excluded as unbounded, unresolved-representation data outside this milestone's scope — recorded in `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_DESIGN.md`. Zero architecture-checker change is required, verified directly against live source. A hostile independent design review found one MAJOR/BLOCKING finding (`M034-DESIGN-REVIEW-0001`): the design conflated `Run.version` (genuine aggregate domain state, advancing via lifecycle transitions and `append_manifest()`) with `LoadedAggregate.persisted_version` (separate repository-loaded concurrency metadata consumed by `save()`), and one MINOR finding (`M034-DESIGN-REVIEW-0002`): an overstatement that a plain dataclass runtime-enforces its annotated field type. A narrow correction distinguished the two version concepts precisely throughout, independently re-evaluated and confirmed the exclusion of `Run.version` from `RunSnapshot` on Run-specific grounds (confusability with `persisted_version`, not M031 symmetry), independently justified the `persisted_version` exclusion against M032's own caller-supplied `expected_persisted_version` precedent, and corrected the dataclass-validation wording — without reopening any other design decision. A final independent design re-review found no CRITICAL or MAJOR finding remaining and concluded **M034 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS** (strengthen implementation test evidence to use deliberately distinguishable `aggregate.version`/`persisted_version` values; `RunSnapshot`'s name remains truthful under its bounded-result definition, no rename required). The owner formally froze the design via `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_DESIGN_FREEZE.md`. MILESTONE-034 implementation delivered exactly `GetRunQuery`/`RunSnapshot`/`GetRunHandler` in `empirical_platform.usecases.get_run`, with 21 new tests (561 total passing, up from 540, zero regression) and zero architecture-checker change. Four PostgreSQL integration tests were written and verified to collect cleanly but were not executed live in this session due to unavailable database credentials and Docker access -- a disclosed limitation, not a hidden gap, recorded in `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_IMPLEMENTATION.md` (Section 24). An independent hostile implementation review subsequently obtained Docker access, reproduced live PostgreSQL evidence (4/4 M034 tests, 122 passed integration regression, 561 passed full suite), and concluded M034 IMPLEMENTATION APPROVED WITH NON-BLOCKING OBSERVATIONS. Every specific claimed result was independently re-verified a third time before freezing, using a fresh disposable PostgreSQL container, with an exact match on every number and the pre-existing setuptools build warning. The owner formally froze the implementation via `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_IMPLEMENTATION_FREEZE.md`. MILESTONE-034 is now `APPROVED_AND_FROZEN` at every stage -- scope, design, and implementation (Section 27). MILESTONE-035 scope -- Concrete Application Command Vertical Slice (Run Lifecycle Transition) -- is a scope candidate (Section 28) after a fresh, from-source architectural-inventory rebuild found that add()/get() have each independently generalized across Campaign and Run (M030/M033, M031/M034), while save()/OptimisticConcurrencyConflict remains proven for Campaign only (M032) and has never been exercised for any second aggregate -- the single largest remaining unproven-generalization gap. Run lifecycle transition was selected over EvidencePackage/Review work (which would repeat an already-twice-proven add()/get() pattern rather than close this gap) using an explicit sixteen-criterion comparison matrix (scope document Sections 9-11). A hostile independent scope review found no CRITICAL, MAJOR, or blocking MINOR finding and concluded **M035 SCOPE APPROVED WITH NON-BLOCKING OBSERVATIONS** (one non-blocking observation: a stale top-level LATEST_FROZEN_MILESTONE=MILESTONE-028 field, never updated across M029-M034, corrected to MILESTONE-034 in this same freeze). The owner formally froze the scope via `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_SCOPE_FREEZE.md`. MILESTONE-035 now has a design candidate (Section 29) -- selecting `Run.authorize()` (CREATED -> AUTHORIZED) as the target transition, a caller-supplied `expected_persisted_version` command field (mirroring M032, rejecting handler-internal reuse of `loaded.persisted_version` as structurally eliminating the stale-write scenario this milestone must prove), `SaveResult` as the result contract, and, independently derived rather than copied from M032, `Run.append_manifest()` as the deterministic PostgreSQL conflict mechanism's interfering write, since Run has no direct analogue to `Campaign.revise_scope_statement()` -- recorded in `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_DESIGN.md`. Zero architecture-checker change is required, verified directly against live source. A hostile independent design review found no CRITICAL, MAJOR, or blocking MINOR finding and concluded **M035 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS** (one non-blocking observation: Section 28 overstated runtime enforcement of DomainIdentity[RunId] generic specialization, corrected to state that only the base identity-pair structure is runtime-validated, with RunId specialization expressed statically only). The owner formally froze the design via `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_DESIGN_FREEZE.md`. MILESTONE-035 implementation delivered exactly `AuthorizeRunCommand`/`AuthorizeRunHandler` in `empirical_platform.usecases.authorize_run`, with 29 new tests (585 total passing, up from 561, zero regression) and zero architecture-checker change. All 5 PostgreSQL integration tests -- including the deterministic `append_manifest()`-based conflict scenario -- were executed live against a fresh disposable container (127 passed on the full integration regression, 712 passed on the full suite with PostgreSQL opt-in), with no disclosed-limitation gap. A final independent hostile implementation review reproduced every gate and concluded **M035 IMPLEMENTATION APPROVED WITH NON-BLOCKING OBSERVATIONS** (secret-scan count drift 385->386, a non-canonical mypy test-file artifact, and transient reviewer tooling friction -- none blocking). The owner formally froze the implementation via `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_IMPLEMENTATION_FREEZE.md`. MILESTONE-035 is now `APPROVED_AND_FROZEN` at every stage -- scope, design, and implementation (Section 30). The owner activated the Macro Milestone Protocol effective from MILESTONE-036 onward (Section 31). MILESTONE-036 -- Concrete Application Command Vertical Slice (EvidencePackage Creation) -- was produced as one consolidated Macro Milestone Mission (Section 32): a fresh architecture inventory found all three CQRS verbs now proven across two aggregates each (Campaign, Run), leaving EvidencePackage/Review as the only aggregates with zero application-layer proof; EvidencePackage creation was selected over a second Run transition, retry policy, and retrieval work (gated behind creation), mirroring M033's own Run-creation pattern one level down the now-fully-proven dependency chain, with the identical persistence-enforced-parent-existence FK mechanism independently re-verified against EvidencePackage's own adapter source. Exactly one narrow architecture-checker addition ("evidence" to ALLOWED["usecases"]) was required, with corresponding fixture maintenance. All PostgreSQL evidence, including the FK-violation scenario, was executed live against a fresh disposable container with zero regression. The next authorized action is MILESTONE-036 INDEPENDENT IMPLEMENTATION REVIEW.

## 11. MILESTONE-029 Scope and Design

**Scope:** Application Service Orchestration — the application invocation boundary that routes commands to `CommandHandler` implementations and queries to `QueryHandler` implementations via two composition-bound entry points, with handler-owned transaction execution and transparent error propagation.

**Why now:** M027-M028 provide the CQRS vocabulary (`CommandHandler` and `QueryHandler` Protocols); M029 provides the orchestration that calls them. Without M029, those Protocols are unreachable abstractions. With M029, every business logic layer above it (APIs, workers, Audit, Decision, market-data execution) becomes possible.

**Dependency chain:**
- M020-M026 (persistence foundation) → provides infrastructure.
- M027-M028 (CQRS contracts) → defines what orchestration calls.
- M029 (orchestration) → routes commands and queries to handlers.
- Later concrete business-handler milestones → define actual commands and handlers.

**Scope selection document:** `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_SCOPE_SELECTION.md` (commit `449d7ef`).

**Scope freeze document:** `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_SCOPE_FREEZE.md` (commit `22cec98`).

**Design document:** `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_DESIGN.md` (commit `f047d3a`) — underwent three independent correction passes before final approval: Pass I corrected an options-catalogue structure into concrete architectural decisions; Pass II restated the exact frozen M024/M025 `run_composed()` contract and resolved transaction/error/handler-resolution decisions; Pass III resolved five remaining blocking findings (architectural emptiness, an unjustified `ApplicationBoundaryError`, unspecified runtime Protocol validation, non-implementable milestone-number architecture rules, and inaccurate async-deferral wording).

**Design freeze document:** `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_DESIGN_FREEZE.md`.

**Status:** Scope APPROVED_AND_FROZEN. Design APPROVED_AND_FROZEN. Implementation APPROVED_AND_FROZEN. MILESTONE-029 is fully complete.

## 12. MILESTONE-029 Implementation Evidence and Owner Freeze

**Implementation commit:** `5b8a7d8a7e6bcd3852161c8fe0fafff5c7f5f986` (`feat: implement M029 application service orchestration`).

**New package:** `src/empirical_platform/application/` — `CommandEntryPoint[CommandT, ResultT]` and `QueryEntryPoint[QueryT, QueryResultT]`, each a composition-bound callable wrapping exactly one frozen M027/M028 handler, invoked exactly once per call, propagating results and exceptions unchanged. No handler discovery, no transaction ownership, no custom exception hierarchy, no runtime Protocol introspection, synchronous only — matching the frozen design at every decision point in Sections 5-9 of `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_DESIGN.md`.

**Architecture enforcement:** `tools/check_architecture.py` extended with an `"application": {"shared"}` allowed-import rule, a `FORBIDDEN_IMPORT_PREFIXES["application"]` entry blocking `empirical_platform.shared.persistence`/`sqlalchemy`/`psycopg`/`boto3`, and `"entrypoints": {"shared", "application"}` permitting transport to depend on the application boundary. Domain feature packages and persistence retain no path to `application` (enforced by omission from their existing allow-lists, unchanged).

**Tests added:** `tests/unit/test_command_entry_point.py`, `tests/unit/test_query_entry_point.py` (behavioral: exactly-once invocation, unchanged input/result/exception identity, natural-failure-on-malformed-handler), `tests/unit/test_application_boundary_invariants.py` (structural: import surface, no exception hierarchy, no runtime introspection, no registry/discovery identifiers, synchronous-only, distinct command/query types), `tests/unit/test_application_boundary_composition.py` (composition/transport-binding pattern), plus three architecture fixtures under `tests/fixtures/illegal_imports/` and two new assertions in `tests/architecture/test_module_boundaries.py`.

**Validation gates (fresh run against implementation):**

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `pytest` suite | PASS — `464 passed, 110 skipped`, coverage `82.85%` (threshold 80%) |
| Focused MILESTONE-029 tests | PASS — `28 passed` |
| Ruff format/check (`src tests tools`) | PASS — 184 files formatted, 0 lint issues |
| mypy strict | PASS — 85 source files (was 82; +3 for the new package) |
| Architecture checker | PASS — 0 violations |
| Build | PASS — sdist and wheel built, `application` package present in wheel contents |

**No M020-M028 frozen contracts changed.** No M029 scope/design/freeze documents changed. No persistence, runtime, or transport implementation added. No MILESTONE-030 work started.

**Independent review history:** The first implementation review found the implementation code conformant but rejected the review package on two evidence/governance defects — a missing external-review ZIP archive and stale contradictory M029 narrative in this document. Both were corrected in commit `a2a64d6bbf166b1d0ef63cbdbb4a6842d50f7ba5` (`docs: correct M029 review governance state`) without touching any source, test, or architecture-rule file. A final independent implementation re-review then evaluated commit `a2a64d6` and found all previously blocking findings resolved, concluding: **M029 IMPLEMENTATION APPROVED FOR OWNER FREEZE.**

**Owner freeze:** The owner formally froze the implementation via `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_IMPLEMENTATION_FREEZE.md`. MILESTONE-029 is now `APPROVED_AND_FROZEN` at every stage: scope, design, and implementation.

**Review status:** COMPLETE. Owner-frozen. No further M029 implementation change is permitted without explicit owner re-authorization, documented reason, independent review where material, and a new governance commit.

**Next permitted action:** MILESTONE-030 INDEPENDENT SCOPE REVIEW (see Section 13).

## 13. MILESTONE-030 Scope (APPROVED_AND_FROZEN)

**Scope:** Concrete Application Command Vertical Slice (Campaign Creation) — one concrete command type and one concrete handler conforming to the frozen M027 `CommandHandler` Protocol, invoked through the frozen M029 `CommandEntryPoint`, persisting a new `Campaign` via the frozen M023 `PostgresCampaignRepository.add()`.

**Why this scope:** Every layer of the CQRS/persistence stack (M020-M029) is frozen, but no two adjacent layers have ever been exercised together with a real, concrete operation — every prior milestone validated its Protocol or boundary exclusively against mock/fake handlers. This is the smallest coherent next capability: one narrow, concrete vertical slice proving the entire frozen stack composes correctly for one real write operation, using `Campaign` because it is the only domain aggregate with zero dependency on any other domain aggregate.

**Explicitly out of scope:** the query-side vertical slice, any other Campaign operation, any other aggregate, any composition-root/registry/DI framework, any transport layer, any retry/optimistic-concurrency handling, and any market-data/vendor/trading/execution behavior.

**Scope document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_SCOPE.md` (commit `2b4ac748304d3859b78b6a1900849fab7b6fec35`).

**Independent review:** A hostile independent scope review, including direct source inspection rather than reliance on the scope document's own claims, found exactly one architectural capability, no hidden design or implementation, no sequencing defect, no bundled capabilities, and no frozen-contract violation. Two non-blocking findings were carried forward for design-phase awareness: `CampaignId`'s governance-value has no frozen generation mechanism (already flagged as an open design question in the scope document), and no currently-allowed package can host a concrete handler needing both the `Campaign` aggregate and `PostgresRepositoryRuntime` without an architecture-checker addition (already narrowly pre-authorized by the scope document's own Scope-Compliance Rules). Decision: **M030 SCOPE APPROVED FOR OWNER FREEZE.**

**Scope freeze document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_SCOPE_FREEZE.md`.

**Status:** `APPROVED_AND_FROZEN`. MILESTONE-030 design is authorized and a candidate now exists (below). MILESTONE-030 implementation is NOT authorized until design is independently reviewed and owner-frozen.

## 14. MILESTONE-030 Design (APPROVED_AND_FROZEN)

**Design document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_DESIGN.md` (design candidate commit `6c12c77fdded4d42caaba1f37287dabf2c5c577a`; correction commit `b0dba94927c8067f0d55aa6790bcf71bb82cb0a6`).

**Selected architecture:** a new top-level package `empirical_platform.usecases` (justified against the already-frozen `datasets: {shared, identifiers, campaign}` precedent in `tools/check_architecture.py`), containing one module `usecases/create_campaign.py` with `CreateCampaignCommand` and `CreateCampaignHandler`. The handler receives `CampaignRepository` and `RuntimeIdentifierGenerator` (both already-frozen Protocols) via constructor injection — and imports nothing from `shared.persistence`, `sqlalchemy`, `psycopg`, or `boto3` anywhere in the package; `CampaignId` is caller-supplied on the command while `runtime_id` is handler-generated; `CommandEntryPoint` binding happens by direct construction in tests only (no new production composition code); all validation is delegated to the already-frozen `Campaign` aggregate and its value objects; all errors propagate transparently, matching M029's frozen invariant exactly. Exactly one *paired* architecture-checker addition is proposed: `ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}` together with `FORBIDDEN_IMPORT_PREFIXES["usecases"] = ("empirical_platform.shared.persistence", "sqlalchemy", "psycopg", "boto3")` — both required together, matching the identical paired-rule shape already used by `campaign`, `run`, `evidence`, `review`, and `application`.

**Independent review and correction:** a hostile independent design review found two MAJOR findings (M030-DESIGN-REVIEW-0001, M030-DESIGN-REVIEW-0002) — the design's Design Question 10 originally and incorrectly claimed `usecases` needed direct `shared.persistence` access, contradicting its own Design Question 3 Protocol-only dependency decision, and consequently omitted the `FORBIDDEN_IMPORT_PREFIXES["usecases"]` entry needed to actually enforce that boundary — and one MINOR finding (M030-DESIGN-REVIEW-0003) in this document's stale narrative. All three were corrected; no other design decision was reopened.

**Final delta re-review:** a final independent hostile design delta re-review independently re-derived the underlying technical problem by hand-tracing `tools/check_architecture.py`'s actual `imported_top_level()`/`check_path()` logic (not merely trusting the correction's own claims), confirmed both cited precedents (`ALLOWED["datasets"]`, and the identical `FORBIDDEN_IMPORT_PREFIXES` tuples `campaign`/`run`/`evidence`/`review`/`application` already carry) exist exactly as claimed, and confirmed via diff-hunk analysis that no other design decision was disturbed. Decision: **M030 DESIGN APPROVED FOR OWNER FREEZE.**

**Design constraints preserved:** domain purity, all existing Protocols/Repository/EntryPoint/Runtime contracts, all existing PostgreSQL adapters, and existing dependency direction — verified against actual frozen source, not assumed. Concrete persistence and runtime objects are supplied to the handler from outside the `usecases` package (by tests, or by a future, separately scoped composition boundary); `usecases` itself never imports or references `PostgresRepositoryRuntime`, `FoundationRuntime`, or `PostgresCampaignRepository`.

**Prohibited items confirmed absent:** no DI framework, registry, service locator, mediator, transport, HTTP, API, queue, scheduler, market-data/trading logic, event bus, command bus, or generic framework.

**Design freeze document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_DESIGN_FREEZE.md`.

**Status:** `APPROVED_AND_FROZEN`. MILESTONE-030 implementation is now authorized, strictly within the boundaries the freeze record establishes.

**Next permitted action:** MILESTONE-030 INDEPENDENT IMPLEMENTATION REVIEW (see Section 15).

## 15. MILESTONE-030 Implementation (Candidate, Not Yet Approved)

**Implementation document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_IMPLEMENTATION.md` (implementation commit `bb66826225f621368ea317b5757631bf94731a56`).

**Implemented:** `CreateCampaignCommand` and `CreateCampaignHandler` in the new `empirical_platform.usecases.create_campaign` module — exactly the vertical slice the frozen design specifies, with no deviation. The handler depends only on the `CampaignRepository` and `RuntimeIdentifierGenerator` Protocols via constructor injection; performs the frozen sequential flow (translate command data into frozen value types, obtain `runtime_id` from the injected generator, construct the `Campaign` aggregate, call `CampaignRepository.add()` exactly once, return `DomainIdentity[CampaignId]`); propagates every collaborator failure transparently; and is invocable through the unmodified, frozen `CommandEntryPoint`.

**Architecture-checker change:** exactly the paired addition the design freeze specifies — `ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}` and `FORBIDDEN_IMPORT_PREFIXES["usecases"] = ("empirical_platform.shared.persistence", "sqlalchemy", "psycopg", "boto3")` — verified both positively (the real implementation passes the full checker) and negatively (7 new fixtures, each triggering exactly one expected violation).

**Tests added:** 14 unit tests (deterministic recording fakes, no mocks), 3 contract tests (Protocol conformance), 3 integration tests against **real PostgreSQL** (a disposable `postgres:17` container via the repository's own `infra/local/compose.yaml`, migrated with the frozen Alembic chain, following the identical opt-in convention `test_m023_postgres_repositories.py` established) proving the golden path and the `AggregateAlreadyExists` failure path end-to-end, plus 7 architecture-checker fixture files and 7 new assertions in `tests/architecture/test_module_boundaries.py`.

**Validation gates (fresh run against the implementation):**

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `pytest` suite, no PostgreSQL opt-in | PASS — 481 passed, 113 skipped, coverage 82.96% |
| Full `pytest` suite, **real PostgreSQL** | PASS — **588 passed**, 6 skipped, coverage **91.87%** |
| Focused M030 tests | PASS — 19 passed |
| Full integration-suite regression check, real PostgreSQL | PASS — 107 passed, 6 skipped |
| Ruff format/check | PASS — 196 files formatted, 0 lint issues |
| mypy strict | PASS — 87 source files (was 85; +2 for `usecases`) |
| Architecture checker (full repo) | PASS — 0 violations |
| Architecture checker (fixtures) | PASS — all 7 new + all pre-existing violations trigger exactly as expected |
| Build | PASS — sdist and wheel built, `usecases` package present in wheel contents |

**Hostile self-audit (executed, not merely asserted):** zero matches anywhere in `src/empirical_platform/usecases/` for `shared.persistence`, `PostgresRepositoryRuntime`, `FoundationRuntime`, `PostgresCampaignRepository`, `sqlalchemy`, `psycopg`, `boto3`, handler-level `try`/`except`, `uuid`/`datetime` identity generation, `run_composed`, or any registry/dispatcher/mediator/service-locator/DI-framework pattern. Exactly 7 imports in `create_campaign.py`, exactly one `.add()` call, exactly 2 modules in the `usecases` package.

**No M020-M029 material changed.** No M030 scope/design/freeze document changed. No transport, query-side, composition-root, or MILESTONE-031 work introduced. No database schema or migration change.

**Independent review:** A hostile independent implementation review verified the 16-file change scope directly against the real commit, re-ran a fresh prohibited-pattern grep sweep (zero matches), independently re-derived the checker's necessity for the paired `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES["usecases"]` rule, read every test for genuine (non-tautological) rigor, and **independently reproduced the real-PostgreSQL evidence from a completely fresh Docker container and volume, twice** — once for the 3 M030-specific integration tests, once for the full 588-test suite — with results identical both times. One non-blocking observation: the typed-conformance tests' "mypy-checked proof" docstring wording is technically imprecise (test files are outside mypy's configured `packages` scope) but is inherited verbatim from M029's own frozen, already-approved tests, not a new defect. Decision: **M030 IMPLEMENTATION APPROVED FOR OWNER FREEZE.**

**Implementation freeze document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_IMPLEMENTATION_FREEZE.md`.

**Review status:** `APPROVED_AND_FROZEN`. MILESTONE-030 is now fully frozen at every stage.

**Next permitted action:** MILESTONE-031 DESIGN MISSION (see Section 16).

## 16. MILESTONE-031 Scope (APPROVED_AND_FROZEN)

**Scope:** Concrete Application Query Vertical Slice (Campaign Retrieval) — one concrete query and one concrete handler conforming to the frozen M028 `QueryHandler` Protocol, invoked through the frozen M029 `QueryEntryPoint`, reading a Campaign via the existing, already-frozen `CampaignRepository.get()` method (M020).

**Why this scope:** M030 proved the write side of the application invocation boundary; the read-side counterpart (`QueryHandler`/`QueryEntryPoint`) has been frozen since M028/M029 but exercised only by mock/fake handlers — a repository-wide search confirms zero concrete query handlers exist anywhere. A Campaign created via M030's slice can currently be read back only by reaching around the application boundary directly. Both M030's own frozen scope document and this checkpoint's prior deferred-capabilities entries explicitly named the query-side vertical slice as the next item.

**Explicitly out of scope:** any `Run`/`EvidencePackage`/`Review` command or query; any Campaign query beyond retrieval-by-identity (no listing/filtering/searching/pagination); any additional Campaign command; any composition-root/registry/dispatcher/caching/read-model/DI framework; any transport layer; any cross-aggregate access; any retry/optimistic-concurrency handling; any market-data/vendor/trading/execution behavior; any MILESTONE-032 work.

**Scope document:** `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_SCOPE.md` (commit `68bd50d1d2e2d38abb3e3e389e4a8dde6d996848`).

**Independent review:** A hostile independent scope review found exactly one coherent read-side capability, correctly following the frozen M030 write-side slice, with every frozen predecessor contract preserved. Two non-blocking governance observations were raised (a `PENDING` scope-commit placeholder; a stale "not yet started" narrative sentence) — both resolved in this same freeze. Decision: **M031 SCOPE APPROVED WITH NON-BLOCKING OBSERVATIONS.**

**Scope freeze document:** `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_SCOPE_FREEZE.md`.

**Status:** `APPROVED_AND_FROZEN`. MILESTONE-031 design was authorized and a candidate now exists (see Section 17). MILESTONE-031 implementation is NOT authorized until design is independently reviewed and owner-frozen.

**Next permitted action:** see Section 17.

## 17. MILESTONE-031 Design (APPROVED_AND_FROZEN)

**Design document:** `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_DESIGN.md` (design candidate commit `f73b924d3c36e4796087aa4bb889a8dcde7b548e`).

**Selected architecture:** one concrete query, `GetCampaignQuery` (single field: `identity: DomainIdentity[CampaignId]`), and one concrete handler, `GetCampaignHandler`, both in a new module `usecases/get_campaign.py` alongside M030's `create_campaign.py`. The handler depends on `CampaignRepository` only via constructor injection (no `RuntimeIdentifierGenerator` — nothing is generated on a read); calls `CampaignRepository.get()` exactly once; and returns a new narrow immutable read value, `CampaignSnapshot` (`identity`, `scope_statement`, `state` — deliberately excluding `persisted_version`), rather than the raw mutable `Campaign` aggregate or the write-metadata-bearing `LoadedAggregate[Campaign]`, to avoid aggregate-mutation leakage and write-side metadata leakage through the read boundary. `AggregateNotFound` and any other repository exception propagate transparently, matching M029's frozen invariant and M030's own precedent. `QueryEntryPoint(GetCampaignHandler(...))` binding is demonstrated by direct construction in tests only, exactly matching M030. No architecture-checker change is required: every needed import (`campaign`, `identifiers`, `shared`) is already covered by M030's existing `ALLOWED["usecases"]` grant.

**Return-shape decision (the design's hardest question):** four options were formally evaluated — (A) return `Campaign` directly, rejected for aggregate-mutability leakage; (B) return `LoadedAggregate[Campaign]` directly, rejected for the same leakage plus exposing write-side `persisted_version` through a read-only boundary; (C) a new narrow immutable read value, selected; (D) another existing frozen type, rejected as no candidate carries exactly `identity + scope_statement + state`. The selection is justified by direct precedent: M030's own `CreateCampaignHandler.handle()` already declined to return the raw `SaveResult`, returning only `campaign.identity` — establishing this project's discipline of extracting the minimal useful slice rather than passing through the underlying repository/contract type verbatim.

**Prohibited items confirmed absent:** no listing/filtering/pagination/sorting, no caching, no generic read-model framework, no hidden DTO/serialization layer, no query registry/dispatcher/mediator/service locator, no DI framework, no composition-root code, no infrastructure import in `usecases`, no not-found translation, no runtime-ID regeneration, no MILESTONE-032 work.

**Hostile self-audit:** performed against the mission's full attack list (unresolved return type, aggregate leakage, accidental read-model framework, hidden DTO layer, governance-ID-only lookup, runtime-ID regeneration, extra repository calls, loss of revision metadata, unauthorized not-found translation, registry/dispatcher leakage, infrastructure dependency, production composition leakage, architecture-checker mismatch, M032 leakage) — no issue survived requiring correction; the one deliberate omission (`persisted_version`) is explicitly justified, not silently dropped.

**Independent review:** A hostile independent design review verified every load-bearing decision directly against actual frozen source (not the design's own claims) — identity semantics, the four-option return-shape evaluation, repository interaction, not-found/error behavior, revision-metadata treatment, and architecture-checker impact — and found zero CRITICAL and zero MAJOR findings. Three non-blocking MINOR findings were raised (an imprecise field-justification sentence in Section 9; an unresolved "or" in the Section 17.F integration-test seed mechanism; incomplete numeric labeling of the ten design questions) and resolved in the design-freeze record without modifying the frozen design document. Decision: **M031 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS.**

**Design freeze document:** `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_DESIGN_FREEZE.md` (freeze commit `196150dcde88610c9bc78e6bd0ff40d4d5da9d9b`).

**Status:** `APPROVED_AND_FROZEN`. MILESTONE-031 implementation was authorized and a candidate now exists (see Section 18).

**Next permitted action:** see Section 18.

## 18. MILESTONE-031 Implementation (APPROVED_AND_FROZEN)

**Implementation document:** `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_IMPLEMENTATION.md` (implementation commit `840310c880f4645ab9a1c9e8219d09b4408f9845`; finalization commit `fb4b52ce521756168f74b660e7846114630b8622`).

**Implemented:** `GetCampaignQuery`, `CampaignSnapshot`, and `GetCampaignHandler` in the new `empirical_platform.usecases.get_campaign` module — exactly the vertical slice the frozen design specifies, with no deviation. The handler depends only on the `CampaignRepository` Protocol via constructor injection; performs the frozen sequential flow (read `query.identity` unchanged, call `CampaignRepository.get()` exactly once, build `CampaignSnapshot` from the loaded aggregate's `identity`/`scope_statement`/`state`, intentionally discarding `persisted_version`); propagates every collaborator failure transparently (no `try`/`except` anywhere in the module); and is invocable through the unmodified, frozen `QueryEntryPoint`.

**Architecture-checker change:** none, exactly as the design freeze predicted. Verified both positively (the real source tree, now including `get_campaign.py`, passes the unmodified checker with 0 violations) and negatively (all 7 pre-existing `usecases`-scoped illegal-import fixtures from M030 still trigger without modification — no new fixture was added, since none was needed).

**Tests added:** 16 unit tests (deterministic recording/failing fakes, no mocks), 3 contract tests (Protocol conformance), 3 integration tests against **real PostgreSQL** (a disposable `postgres:17` container, following the identical opt-in convention `test_m030_create_campaign_usecase.py` established) proving the golden path (retrieval of a Campaign created via the frozen M030 slice) and the `AggregateNotFound` failure path end-to-end.

**Validation gates (fresh run against the implementation):**

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `pytest` suite, no PostgreSQL opt-in | PASS — 500 passed, 116 skipped, coverage 83.07% |
| Full `pytest` suite, **real PostgreSQL** | PASS — **610 passed**, 6 skipped, coverage **91.92%** |
| Focused M031 tests (unit + contract) | PASS — 19 passed |
| Focused M031 PostgreSQL integration | PASS — 3 passed |
| Full integration-suite regression check, real PostgreSQL | PASS — 110 passed, 6 skipped |
| Ruff format/check | PASS — 200 files formatted, 0 lint issues |
| mypy strict | PASS — 88 source files (was 87; +1 for `get_campaign.py`) |
| Architecture checker (full repo) | PASS — 0 violations |
| Architecture checker (fixtures) | PASS — all pre-existing `usecases` violations trigger exactly as before, unmodified |
| Build | PASS — sdist and wheel built, `get_campaign.py` present in wheel contents |
| Security — pip-audit | PASS — no known vulnerabilities |
| Security — secret scan targets | PASS — 345 targets discovered |

**Hostile self-audit (executed, not merely asserted):** zero matches anywhere in `src/empirical_platform/usecases/get_campaign.py` for `shared.persistence`, `PostgresRepositoryRuntime`, `FoundationRuntime`, `PostgresCampaignRepository`, `sqlalchemy`, `psycopg`, `boto3`, `try:`/`except`, `run_composed`, registry/dispatcher/mediator/service-locator patterns, `async`, `uuid`/`datetime` identity generation, or any listing/filtering/pagination/caching/transport keyword. Exactly 5 imports, exactly one `.get(` call, exactly 45 lines.

**No M020-M030 material changed.** No M031 scope/design/freeze document changed. No transport, composition-root, or MILESTONE-032 work introduced. No database schema or migration change.

**Independent review:** A hostile independent implementation review verified the 7-file (implementation) + 2-file (finalization) change scope directly against the real commits, re-ran a fresh prohibited-pattern grep sweep (zero matches), independently re-verified the architecture-checker preservation claim, read all 22 tests for genuine (non-tautological) rigor, and **independently reproduced the real-PostgreSQL evidence from a completely fresh Docker container, twice** — once for the 3 M031-specific integration tests, once for the full 610-test suite and full integration regression — with results identical both times. It also independently re-extracted and re-verified the external review package's manifest (74/74 hashes) and ZIP from a fresh extraction. Two non-blocking observations were raised (a miscounted test total — 22, not 23; a stale secret-scan target count — 345, not 344) and resolved in this same freeze. No CRITICAL or MAJOR finding. Decision: **M031 IMPLEMENTATION APPROVED WITH NON-BLOCKING OBSERVATIONS.**

**Implementation freeze document:** `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_IMPLEMENTATION_FREEZE.md` (freeze commit `f144c963f6bcf90a8ada5cf14853fce5e73d48d8`).

**Review status:** `APPROVED_AND_FROZEN`. MILESTONE-031 is now fully frozen at every stage.

**Next permitted action:** see Section 19.

## 19. MILESTONE-032 Scope (APPROVED_AND_FROZEN)

**Scope document:** `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_SCOPE.md` (scope candidate commit `5ea62d02d65945f0976e42b8c011217d895723e4`).

**Selected scope:** Concrete Application Command Vertical Slice (Campaign Lifecycle Transition) — one concrete command and one concrete handler conforming to the frozen M027 `CommandHandler` Protocol, invoked through the frozen M029 `CommandEntryPoint`, persisting a Campaign lifecycle-state transition via the frozen M023 `PostgresCampaignRepository.save()` method for the first time anywhere in the application layer.

**Verified gap (evidence-driven, not assumed):** an 18-point architectural inventory across domain aggregates, repository Protocols, PostgreSQL adapters, transaction/runtime composition, CQRS contracts, existing use cases, transport, error/concurrency behavior, and every `PROJECT_CHECKPOINT.md` deferred-capability entry found that `CampaignRepository.save()` and the `OptimisticConcurrencyConflict` contract it guards — frozen since M020/M023 — have zero application-layer proof: `CreateCampaignHandler` (M030) calls only `add()`, `GetCampaignHandler` (M031) calls only `get()`. Both M030's own frozen scope (Deferred Work: "Retry-on-`OptimisticConcurrencyConflict` policy (requires a "save" operation on an existing aggregate, which this milestone does not include)") and M031's own deferred-capabilities entry ("retry-on-`OptimisticConcurrencyConflict` policy after a concrete handler exists that saves an existing aggregate") name this exact gap as the next dependency — both citations independently verified verbatim against the real frozen documents during scope review.

**Candidates considered and rejected:** retry-policy foundation (blocked on this milestone existing first, per M030's own text); composition-root wiring (repeated-handler-need evidence bar not yet met); a second aggregate's command or query vertical slice (would repeat an already-proven pattern instead of closing the more architecturally significant `save()` gap); a transport-neutral invocation adapter (silently depends on the rejected composition-root candidate). Full comparison matrix and evidence-based rejection reasons recorded in the scope document Sections 6-8.

**Explicitly out of scope:** any retry/backoff/idempotency policy; any `Run`/`EvidencePackage`/`Review` command or query; any additional Campaign command beyond the one targeted lifecycle transition; any composition-root/registry/dispatcher/DI framework; any transport layer; any market-data/vendor/trading/execution behavior; any MILESTONE-033 work.

**Open design questions (explicitly not resolved by scope):** which specific `Campaign` lifecycle-transition method is targeted; how the handler obtains a valid `expected_persisted_version` for `save()`; the exact command/handler type names and shapes; whether any architecture-checker change is needed (expected: none).

**Independent review:** A hostile independent scope review verified repository truth, the frozen predecessor chain, the architectural inventory, the claimed gap (independently reproven from primary source via direct repository search, not merely asserted), candidate comparison and sequencing, scope purity, absence of hidden design/implementation, and frozen-contract preservation. It found three non-blocking documentation findings — two citations of M030/M031 predecessor text that used quotation marks around paraphrased rather than verbatim wording, and one internal 7-vs-8-method terminology inconsistency for `Campaign` — none affecting the substance of the selection. Decision: **APPROVED FOR OWNER SCOPE FREEZE.**

**Scope freeze document:** `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_SCOPE_FREEZE.md` (freeze commit `b18878a514694d6663026e11d98859023c04a136`).

**Status:** `APPROVED_AND_FROZEN`. MILESTONE-032 design was authorized and a candidate now exists (see Section 20). MILESTONE-032 implementation is NOT authorized until design is independently reviewed and owner-frozen.

**Next permitted action:** see Section 20.

## 20. MILESTONE-032 Design (APPROVED_AND_FROZEN)

**Design document:** `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_DESIGN.md` (design candidate commit `50f2cd829af2e10799ab3581b4c2e56e9e04d401`).

**Selected architecture:** one concrete command, `PrepareCampaignForAuthorizationCommand` (fields: `identity: DomainIdentity[CampaignId]`, `expected_persisted_version: AggregateVersion`, `actor: str`, `occurred_at: datetime`, `correlation_id: str | None = None`, `reason: str | None = None`), and one concrete handler, `PrepareCampaignForAuthorizationHandler`, both in a new module `usecases/prepare_campaign_for_authorization.py` alongside M030's/M031's existing use cases. The handler depends on `CampaignRepository` only via constructor injection; performs exactly one `get()` → one `Campaign.prepare_for_authorization()` mutation → one `save()` sequence; returns the frozen `SaveResult` type unchanged. No architecture-checker change is required.

**Mutation selection (systematic, 8 candidates evaluated):** five of `Campaign`'s eight mutation methods (`record_authorization`, `activate`, `suspend`, `resume`, `complete`) were disqualified outright — each requires a lifecycle state unreachable from a freshly-created Campaign without one or more prior `save()` calls, violating the frozen "one load→mutate→save path" scope boundary. Of the three remaining DRAFT-reachable candidates, `prepare_for_authorization()` was selected over `revise_scope_statement` (which never changes lifecycle state, undercutting the milestone's own frozen name) and `cancel()` (a terminal "exit" transition, architecturally peripheral compared to the lifecycle's literal first forward transition).

**Expected-version decision (the design's hardest question):** the command carries a caller-supplied `expected_persisted_version`, independent of whatever the handler's own `get()` call happens to return — the only model that keeps the `OptimisticConcurrencyConflict` path honestly and deterministically testable in a sequential test (a handler-derived version would make conflicts structurally unreachable without an unauthorized interleaving hook). The conflict scenario's exact interfering-write mechanism (`Campaign.revise_scope_statement()` on an independently loaded aggregate, rather than `prepare_for_authorization()` itself) was corrected following independent design review (see below).

**Return contract:** the frozen `SaveResult` type (`operation`, `persisted_version`), returned unchanged — justified as the write-side counterpart to M031's read-side `CampaignSnapshot` reasoning: a write-side caller genuinely needs the *new* persisted version to perform a correct follow-up write, unlike M031's pure-read case, which had no such need.

**Prohibited items confirmed absent:** no retry/backoff, no second mutation, no `Run`/`EvidencePackage`/`Review` work, no composition root/registry/dispatcher/service locator/DI framework, no transport, no `Clock` collaborator, no shared transaction spanning `get()`/`save()`, no MILESTONE-033 work.

**Hostile self-audit:** performed against the mission's full attack list (invalid initial state, unresolved version source, impossible conflict reproduction, hidden retry, hidden second capability, lost version metadata, persistence-shaped return leakage, extra repository calls, missing write suppression after domain failure, unauthorized transaction orchestration, generic lifecycle abstraction, infrastructure import, architecture-checker mismatch, production composition leakage, M033 leakage) — no issue survived requiring correction.

**Independent review and correction:** A hostile independent design review verified every load-bearing decision directly against actual frozen source (not the design's own claims) — mutation selection, command contract, expected-version ownership, the exact `save()` concurrency guard, return contract, transaction ownership, and architecture impact — and found the design's claim that its PostgreSQL conflict scenario "mirrors M023's own already-proven test" to be inaccurate: direct inspection of the real M023 test showed it uses a fundamentally different mechanism that does not transfer to a single-mutation command, and the design's original scenario 2, if implemented literally, would raise a domain `ValueError` (via a naive reuse of `prepare_for_authorization()` as the interfering write) rather than the intended `OptimisticConcurrencyConflict` — finding **M032-DESIGN-REVIEW-0001**, MAJOR. No CRITICAL finding; every other decision (mutation selection, expected-version ownership model, return contract, transaction ownership, architecture impact) was independently verified sound. Decision: **M032 DESIGN REQUIRES CORRECTION.** A narrow correction pass resolved the finding by specifying `Campaign.revise_scope_statement()` — performed through an independently loaded aggregate for the same identity — as the interfering write, with an explicit explanation of why `prepare_for_authorization()` cannot serve that role (it would invalidate its own domain precondition before the command under test reaches the concurrency check). No other design decision was reopened.

**Final independent design re-review:** confirmed the corrected conflict mechanism (`revise_scope_statement()` as the interfering write) is genuine and deterministic, that no other design decision was disturbed by the correction, and that the design introduces no second application capability. It raised one non-blocking observation, **M032-DESIGN-RE-REVIEW-0001**: residual wording elsewhere in the document (Section 11's reasoning and the Section 28 risk table) still claimed the conflict path "directly mirrors" M023's test pattern without the M032-specific qualification the corrected Section 21 already carried. Decision: **M032 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS.** The residual wording was corrected in this same freeze mission (Option A) to consistently state that M032 uses the same frozen repository concurrency semantics M023 proves, adapted with an M032-specific, state-preserving interfering write — no architectural decision was altered.

**Design freeze document:** `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_DESIGN_FREEZE.md` (freeze commit `14204e4c24024fa7e1d56fbf49dccef0a1fa6a58`).

**Status:** `APPROVED_AND_FROZEN`. MILESTONE-032 implementation was authorized and a candidate now exists (see Section 21).

**Next permitted action:** see Section 21.

## 21. MILESTONE-032 Implementation (APPROVED_AND_FROZEN)

**Implementation document:** `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_IMPLEMENTATION.md` (implementation commit `2901a6e7f6c305a86a8ba7635a436c9299433519`; finalization commit `8db4febca15299861103c26f716d19b3a5d5bd29`).

**Implemented:** `PrepareCampaignForAuthorizationCommand` and `PrepareCampaignForAuthorizationHandler` in the new `empirical_platform.usecases.prepare_campaign_for_authorization` module — exactly the vertical slice the frozen design specifies, with no deviation. The handler depends only on `CampaignRepository` via constructor injection; performs the frozen sequential flow (`get()` exactly once, `Campaign.prepare_for_authorization()` exactly once with the command's own `actor`/`occurred_at`/`correlation_id`/`reason`, `save()` exactly once with the mutated aggregate and the command's own `expected_persisted_version` — never `loaded.persisted_version`); propagates every collaborator failure transparently (no `try`/`except` anywhere); returns the exact `SaveResult` `save()` produced, unchanged; and is invocable through the unmodified, frozen `CommandEntryPoint`.

**Architecture-checker change:** none, exactly as the design freeze predicted. Verified both positively (the real source tree, now including the new module, passes the unmodified checker with 0 violations) and negatively (all 7 pre-existing `usecases`-scoped illegal-import fixtures from M030 still trigger without modification).

**Tests added:** 19 unit tests (deterministic recording/failing fakes, no mocks — including an explicit test proving `save()` receives the command's `expected_persisted_version`, never `loaded.persisted_version`), 3 contract tests (Protocol conformance), 3 integration tests against **real PostgreSQL** proving the golden path, the deterministic `OptimisticConcurrencyConflict` scenario (`revise_scope_statement()` as the interfering write, per Design Freeze Section 25), and the domain-invalid-transition path.

**Validation gates (fresh run against the implementation):**

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `pytest` suite, no PostgreSQL opt-in | PASS — 522 passed, 119 skipped, coverage 83.18% |
| Full `pytest` suite, **real PostgreSQL** | PASS — **635 passed**, 6 skipped, coverage **91.98%** |
| Focused M032 tests (unit + contract) | PASS — 22 passed |
| Focused M032 PostgreSQL integration | PASS — 3 passed |
| Full integration-suite regression check, real PostgreSQL | PASS — 113 passed, 6 skipped |
| Ruff format/check | PASS — 204 files formatted, 0 lint issues |
| mypy strict | PASS — 89 source files (was 88; +1) |
| Architecture checker (full repo) | PASS — 0 violations |
| Architecture checker (fixtures) | PASS — all pre-existing `usecases` violations trigger exactly as before, unmodified |
| Build | PASS — sdist and wheel built, new module present in wheel contents |
| Security — pip-audit | PASS — no known vulnerabilities |
| Security — secret scan targets | PASS — 355 targets discovered |

**Hostile self-audit (executed, not merely asserted):** zero matches anywhere in the new production module for `shared.persistence`, `PostgresRepositoryRuntime`, `FoundationRuntime`, `PostgresCampaignRepository`, `sqlalchemy`, `psycopg`, `boto3`, `try:`/`except`, registry/dispatcher/mediator/service-locator patterns, `.add(`, `.delete(`, or any Campaign mutation method other than `prepare_for_authorization()` (`revise_scope_statement`, `record_authorization`, `activate`, `suspend`, `resume`, `complete`, `cancel` are all absent from production code — `revise_scope_statement()` appears only in the integration test's interfering-write setup). Exactly one `.get(`, one `.save(`, one `prepare_for_authorization(` call.

**No M020-M031 material changed.** No M032 scope/design/freeze document changed. No transport, composition-root, or MILESTONE-033 work introduced. No database schema or migration change.

**Independent review:** A hostile independent implementation review verified the 7-file (implementation) + 2-file (finalization) change scope directly against the real commits, re-ran a fresh prohibited-pattern grep sweep (zero matches, including confirming no Campaign mutation other than `prepare_for_authorization()` appears in production code), read all 25 tests for genuine (non-tautological) rigor, and **independently reproduced the real-PostgreSQL evidence from a fresh Docker container** — the golden path, the deterministic `OptimisticConcurrencyConflict` scenario, and the invalid-transition path — with results identical to the implementation's own claims. It also independently re-extracted and re-verified the external review package's manifest (77/77 hashes) and ZIP from a fresh extraction. No CRITICAL or MAJOR finding. No correction required. Decision: **M032 IMPLEMENTATION APPROVED FOR OWNER FREEZE.**

**Implementation freeze document:** `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_IMPLEMENTATION_FREEZE.md` (freeze commit `84fcf35082aafc1a02358f2e3aa8f7de81841cc9`).

**Review status:** `APPROVED_AND_FROZEN`. MILESTONE-032 is now fully frozen at every stage.

**Next permitted action:** see Section 22.

## 22. MILESTONE-033 Scope (APPROVED_AND_FROZEN)

**Scope document:** `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_SCOPE.md` (scope candidate commit `04e274240f7958d80bc0cb87f92f825b563fbd5a`).

**Selected scope:** Concrete Application Command Vertical Slice (Run Creation) — one concrete command and one concrete handler conforming to the frozen M027 `CommandHandler` Protocol, invoked through the frozen M029 `CommandEntryPoint`, persisting a new `Run` via the frozen M023 concrete `Run` repository adapter's `add()` method — the first application-layer capability for any aggregate other than `Campaign`.

**Verified gap (evidence-driven, not assumed):** an 18-point architectural inventory (aggregates, repository Protocols, concrete PostgreSQL adapters, transaction/runtime composition, CQRS contracts, existing use cases, the `usecases` architecture-checker boundary, cross-aggregate dependency graph, transport, composition-root readiness, and the current `PROJECT_CHECKPOINT.md` deferred-capabilities list) found that `Campaign`'s application-layer proof is now structurally complete (`add()` proven by M030, `get()` by M031, `save()`+`OptimisticConcurrencyConflict` by M032), while `Run`, `EvidencePackage`, and `Review` — despite already having identical, frozen repository Protocols (M020) and concrete PostgreSQL adapters (M023) — have zero application-layer proof of any kind, independently verified by a repository-wide search finding zero references to any of the three anywhere in `src/empirical_platform/usecases/`. Unlike the M031→M032 transition, no single frozen document names this gap over a fourth Campaign-only milestone as the explicit next step; `PROJECT_CHECKPOINT.md`'s own deferred-capabilities list (Section 9, prior revision) named both with equal weight, so this selection rests on independent comparative analysis rather than an explicit breadcrumb.

**Candidates considered and rejected:** a fourth Campaign-only command (`record_authorization()` — repeats an already-proven pattern a third time, adding no new architectural proof); `EvidencePackage`/`Review` creation (same generalization proof as `Run`, but one or two dependency-graph hops further from the only fully-proven aggregate); the retry-on-conflict policy (only one concrete conflict-producing command exists — insufficient evidence to generalize without repeating the premature-abstraction mistake M030-M032 each explicitly avoided); composition-root wiring (the repeated-handler-need evidence bar this repository has consistently applied remains unmet — three handlers, one aggregate, one unchanging trivial binding pattern); transport (silently depends on the rejected composition-root candidate); audit/registry/governance work (each is an empty stub requiring an entire new foundational milestone chain before any command/query work is possible). Full nine-criterion comparison matrix and evidence-based rejection reasons recorded in the scope document Sections 6-8.

**Why `Run` over `EvidencePackage`/`Review`:** direct inspection of each aggregate's constructor dependencies confirms a strict linear chain — `Run` references only `CampaignId` (the identifier of the one aggregate already fully proven); `EvidencePackage` references `RunId`; `Review` references `EvidencePackageId`. `Run` is therefore the least cross-aggregate-dependent of the three unproven aggregates, directly mirroring M030's own original "narrowest available subject" reasoning for selecting `Campaign` itself.

**Explicitly out of scope:** any Run lifecycle-transition command; any Run query; any additional Campaign command or query beyond M030-M032; any command or query for `EvidencePackage` or `Review`; any composition-root/registry/dispatcher/DI framework; any transport layer; any retry/idempotency policy; any market-data/vendor/trading/execution behavior; any MILESTONE-034 work.

**Open design questions (explicitly not resolved by scope):** the exact command/handler type names and shapes; whether the command carries a raw governance-identifier string or the frozen `CampaignId`/`DomainIdentity[CampaignId]` type directly; whether the handler validates the referenced Campaign exists before creating the Run; the runtime-ID generation mechanism for the new Run's identity; the exact, minimal `tools/check_architecture.py` addition required (expected: adding `"run"` to `ALLOWED["usecases"]`, mirroring M030's own addition shape).

**Independent review:** A hostile independent scope review verified repository truth, the exact governance-only delta, the real absence of any Run application usecase, Run aggregate and repository readiness, PostgreSQL Run adapter readiness, cross-aggregate dependency shape, Campaign-existence validation left correctly as an open design question rather than a hidden second scope, the architecture-checker impact framed as a likely narrow future extension rather than a frozen decision, identity-generation questions left correctly to design, frozen-contract preservation, testability, and governance consistency. No CRITICAL, MAJOR, or blocking MINOR finding was found; no correction was required. Decision: **M033 SCOPE APPROVED FOR OWNER FREEZE.**

**Scope freeze document:** `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_SCOPE_FREEZE.md` (freeze commit `44dd29e34f6150bd37bc466eed14098d75ac57ab`).

**Status:** `APPROVED_AND_FROZEN`. MILESTONE-033 design was authorized and a candidate now exists (see Section 23). MILESTONE-033 implementation is NOT authorized until design is independently reviewed and owner-frozen.

**Next permitted action:** see Section 23.

## 23. MILESTONE-033 Design (APPROVED_AND_FROZEN)

**Design document:** `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_DESIGN.md` (design candidate commit `8edead3bc25d786cef8563f4fc4815a889a3a447`).

**Selected architecture:** one concrete command, `CreateRunCommand` (fields: `run_governance_id: str`, `campaign_governance_id: str`), and one concrete handler, `CreateRunHandler`, both in a new module `usecases/create_run.py`. The handler depends on `RunRepository` and `RuntimeIdentifierGenerator` only via constructor injection — no `CampaignRepository`; performs exactly one `RunId`/`CampaignId` construction, one `runtime_id` generation, one `Run` construction, one `RunRepository.add()` call; returns `DomainIdentity[RunId]`, mirroring M030's own return-shape reasoning exactly.

**Campaign existence decision (the design's hardest question):** no application-level Campaign lookup. Direct inspection of `migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py` confirmed a real foreign-key constraint (`run.campaign_id → campaign.governance_id`); direct inspection of `PostgresRunRepository.add()` and the `_errors.py` unique-violation helper confirmed a foreign-key violation is *not* one of the unique-violation constraints that helper special-cases, so it re-raises as an unmodified `FoundationError` (category `PERSISTENCE`) — a fully deterministic, transparently-propagating failure requiring zero extra repository call and zero `CampaignRepository` dependency, selected over a redundant, race-exposed handler-level pre-check.

**Identity model:** caller-supplied governance `RunId` (raw string on the command) plus handler-generated `runtime_id` via the injected `RuntimeIdentifierGenerator`, directly mirroring M030's `CreateCampaignCommand`/`CreateCampaignHandler` precedent.

**Architecture-checker impact:** exactly one line — `"run"` added to `ALLOWED["usecases"]` (verified directly against the live `tools/check_architecture.py`; `FORBIDDEN_IMPORT_PREFIXES["usecases"]` already exists and needs no change) — narrower than M030's own original two-part addition.

**Prohibited items confirmed absent:** no Run retrieval, no Run lifecycle transition, no second Run command, no Campaign mutation/query, no `EvidencePackage`/`Review` work, no composition root/registry/dispatcher/service locator/DI framework, no transport, no `run_composed()`, no MILESTONE-034 work.

**Hostile self-review:** performed against the mission's full attack list (hidden Campaign validation, unresolved existence behavior, invalid foreign-key assumptions, unresolved identity source, runtime-ID ambiguity, duplicate-identity ambiguity, return-contract leakage, architecture-checker mismatch, extra repository calls, transaction overreach, generic creation abstraction, production composition leakage, second-aggregate behavior, M034 leakage) — no issue survived requiring correction.

**Independent review:** A hostile independent design review verified every load-bearing decision directly against actual frozen source — `Run` aggregate creation semantics, `RunRepository.add()`, `PostgresRunRepository.add()`, the real database foreign-key behavior, duplicate-identity translation, raw `FoundationError` propagation for a missing Campaign, the identity-generation model, the exact command/handler contracts, the exact creation sequence, the return contract, transparent error behavior, the absence of transaction orchestration, the narrow architecture-checker extension, and the PostgreSQL evidence strategy. No CRITICAL, MAJOR, or blocking MINOR finding was found; no correction was required. One non-blocking observation was preserved, not corrected: the missing-Campaign behavior intentionally exposes the existing `FoundationError` (category `PERSISTENCE`) the frozen persistence layer already produces, consistent with M029's transparent-error-propagation principle. Decision: **M033 DESIGN APPROVED FOR OWNER FREEZE.**

**Design freeze document:** `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_DESIGN_FREEZE.md` (freeze commit `ec802143626e850dafe70ce9f0f561fa8516df94`).

**Status:** `APPROVED_AND_FROZEN`. MILESTONE-033 implementation was authorized and a candidate now exists (see Section 24).

**Next permitted action:** see Section 24.

## 24. MILESTONE-033 Implementation (APPROVED_AND_FROZEN)

**Implementation document:** `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_IMPLEMENTATION.md` (implementation commit `59fb2ffaa244886990bf68da018c138777a209f0`).

**Implemented:** `CreateRunCommand` and `CreateRunHandler` in the new `empirical_platform.usecases.create_run` module — exactly the vertical slice the frozen design specifies, with no deviation. The handler depends only on `RunRepository` and `RuntimeIdentifierGenerator` via constructor injection (verified structurally: no `campaign_repository` parameter exists); performs the frozen sequential flow (`RunId` construction, one `generate()` call, `DomainIdentity` construction, `CampaignId` construction, one `Run` construction, one `RunRepository.add()` call); returns `run.identity` unchanged; propagates every collaborator failure transparently (no `try`/`except` anywhere); and is invocable through the unmodified, frozen `CommandEntryPoint`.

**Architecture-checker change:** exactly the one line the design freeze specifies — `"usecases": {"shared", "identifiers", "campaign", "run"}`. The now-obsolete `bad_run_import.py` fixture (which asserted `usecases` could not import `run`) was removed and replaced with `bad_evidence_import.py` (proving `usecases` still cannot import `evidence`) and a new `run/bad_usecases_import.py` fixture (proving the reverse-direction boundary remains intact) — both narrowly justified consequences of the authorized checker change, not scope expansion.

**Tests added:** 15 unit tests, 3 contract tests (deterministic recording/failing fakes, no mocks), 5 real-PostgreSQL integration tests covering the golden path, duplicate-governance-ID failure, duplicate-runtime-ID failure, missing-Campaign foreign-key failure, and a no-composition-machinery check (23 tests total), plus 2 new architecture fixtures.

**Validation gates (fresh run against the implementation):**

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `pytest` suite, no PostgreSQL opt-in | PASS — 540 passed, 124 skipped, coverage 83.28% |
| Full `pytest` suite, **real PostgreSQL** | PASS — **658 passed**, 6 skipped, coverage **92.08%** |
| Focused M033 tests (unit + contract + architecture) | PASS — 20 passed |
| M033 PostgreSQL integration tests | PASS — 5 passed |
| Full integration-suite regression, real PostgreSQL | PASS — 118 passed, 6 skipped |
| M030-M032 + M023 Run-specific regression, real PostgreSQL | PASS — 35 passed |
| Ruff format/check | PASS — 209 files formatted, 0 lint issues |
| mypy strict | PASS — 90 source files (was 89; +1) |
| Architecture checker (full repo) | PASS — 0 violations |
| Architecture checker (fixtures) | PASS — updated assertions trigger exactly as expected |
| Build | PASS — sdist and wheel built, new module present in wheel contents |
| Security — pip-audit | PASS — no known vulnerabilities |
| Security — secret scan targets | PASS — 366 targets discovered |

**Hostile self-audit (executed, not merely asserted):** zero genuine matches anywhere in `src/empirical_platform/usecases/create_run.py` for `CampaignRepository`, `shared.persistence`, `PostgresRunRepository`, `FoundationRuntime`, `sqlalchemy`, `psycopg`, `boto3`, `try:`/`except`, `run_composed`, any Run lifecycle-transition method, `.get(`/`.save(` calls, registry/dispatcher/mediator/service-locator patterns, `EvidencePackage`/`Review`, or MILESTONE-034 references. Exactly 7 imports, exactly one `.generate()` call, exactly one `.add()` call, zero `campaign` package import.

**No M020-M032 material changed.** No M033 scope/design/freeze document changed. No transport, composition-root, or MILESTONE-034 work introduced. No database schema or migration change.

**Independent review and correction:** An initial hostile independent implementation review found the production implementation, tests, architecture, and PostgreSQL behavior technically sound, but found the external-review package untrustworthy — concluding **M033 IMPLEMENTATION REQUIRES CORRECTION** (two MAJOR findings: a stale `complete.diff` still showing `M033_IMPLEMENTATION_COMMIT=PENDING`, and a stale pre-push `repository-truth.txt`; two MINOR findings: an incorrect narrative test count — 16 unit/24 total reported vs. the actual 15 unit/3 contract/5 integration/23 total — and an incorrect secret-scan target count — 365 reported vs. the actual 366). A narrow evidence-only correction (commit `18dabb8966a0b54572aea684e4a5075448052bc0`, `docs: correct M033 implementation evidence counts`) corrected both tracked documents and fully regenerated the external-review package against the synchronized post-push HEAD, touching no production source, test, checker, fixture, schema, migration, or frozen M033 authority document. A final independent implementation re-review verified all four findings fully resolved — `complete.diff` byte-identical to the corrected final diff, `repository-truth.txt` synchronized, corrected counts independently reproduced, 51/51 manifest hashes verified, ZIP integrity validated, all technical regression gates re-confirmed, no new finding — concluding **M033 IMPLEMENTATION APPROVED FOR OWNER FREEZE.**

**Implementation freeze document:** `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_IMPLEMENTATION_FREEZE.md` (freeze commit `38ed45518d8a2068d29e7375c2c09ea2af80963c`).

**Review status:** `APPROVED_AND_FROZEN`. MILESTONE-033 is now fully frozen at every stage.

**Next permitted action:** see Section 25.

## 25. MILESTONE-034 Scope (APPROVED_AND_FROZEN)

**Scope document:** `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_SCOPE.md` (scope candidate commit `3ee8485143f1397cad9d14bc55744e97f60aa9d3`).

**Selected scope:** Concrete Application Query Vertical Slice (Run Retrieval) — one concrete query and one concrete handler conforming to the frozen M028 `QueryHandler` Protocol, invoked through the frozen M029 `QueryEntryPoint`, reading a Run via the existing, already-frozen `RunRepository.get()` method (M020) — the first application-layer read-side capability for any aggregate other than `Campaign`.

**Verified gap (evidence-driven, not assumed):** an 18-point architectural inventory, rebuilt entirely fresh from source in this mission, found that `CommandHandler`/`CommandEntryPoint` generalization to a second aggregate is now proven (M033, via `Run` creation's `add()` call), while `QueryHandler`/`QueryEntryPoint` generalization remains completely unproven for any aggregate beyond `Campaign` — independently re-verified by direct repository search finding `GetCampaignHandler` (M031) is still the only concrete query handler that has ever existed anywhere in the codebase.

**Candidates considered and rejected:** a Run lifecycle-transition command (a real future candidate, but a harder write-side generalization question requiring its own multi-candidate mutation analysis, and a departure from this project's established create→read→update sequencing discipline for one aggregate); `EvidencePackage` creation (dependency-ready but architecturally weaker — `add()`-based creation has already been proven to generalize across two aggregates, so a third instance answers no open question); `Review` creation (two dependency hops from ready); retry policy, composition-root wiring, and transport (all rejected on unchanged reasoning from M032/M033). Full nine-column comparison matrix and evidence-based rejection reasons recorded in the scope document Sections 6-8.

**Explicitly out of scope:** any Run mutation or lifecycle-transition command; any command or query for `EvidencePackage` or `Review`; any additional Campaign command or query beyond M030-M032; any composition-root/registry/dispatcher/DI framework; any transport layer; any listing/filtering/pagination; any MILESTONE-035 work.

**Open design questions (explicitly not resolved by scope):** the exact query/handler type names and shapes; the exact result contract — its type and representation (raw `Run`, `LoadedAggregate[Run]`, an existing frozen type, a new narrow milestone-local type, or another justified shape) and, once chosen, which fields or data it carries; whether write-side metadata (e.g. `persisted_version`) is included or excluded. None of this is selected or preferred by the scope; it is resolved during the Design Mission.

**Correction:** an independent hostile scope review (finding `M034-SCOPE-REVIEW-0001`, MAJOR/BLOCKING) found the original scope document prematurely committed the retrieval result to a "read value" / "immutable, milestone-local read value" shape in Sections 9 and 13. This was corrected via commit `60178d3d1caf96d1fe33f318e57e94c708e8896f` (scope document unchanged in selected capability; result-shape language made neutral) — see the scope document's Section 1 correction history.

**Final independent scope re-review:** verified repository truth, the correction-only two-file delta, reproduction of the original blocking finding, full removal of the premature result-shape commitment, true result-shape neutrality, preservation of exactly one Run retrieval capability, full `DomainIdentity[RunId]` repository truth, existing `AggregateNotFound` repository behavior, no hidden design replacement, no architecture-boundary change, sequencing correctness, independent testability, checkpoint consistency, and that no MILESTONE-035 work exists. Decision: **M034 SCOPE APPROVED FOR OWNER FREEZE.** The owner formally froze the scope via `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_SCOPE_FREEZE.md`.

**Status:** `APPROVED_AND_FROZEN`. Design has a candidate (Section 26); implementation is not yet started.

**Next permitted action:** see Section 26.

## 26. MILESTONE-034 Design (APPROVED_AND_FROZEN)

**Design document:** `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_DESIGN.md` (design candidate commit `d343e38cba9b5a49db278c72ca1650dd50839bd2`; correction commit `993144e4361372e6978b11d96d6e1fe98e722c73`).

**Query identity model:** `GetRunQuery` carries the full `DomainIdentity[RunId]` the frozen `RunRepository.get()` already requires — selected over a split-field model (unnecessary translation), a raw-string model (would force an unused `RuntimeIdentifierGenerator` dependency, unlike M033's `CreateRunCommand` which genuinely needs one to mint a new runtime id), and a governance-ID-only model (no resolution mechanism exists anywhere in the frozen codebase).

**Result contract (the central load-bearing decision):** a new milestone-local `RunSnapshot` (`identity`, `campaign_id`, `state` — three fields, frozen/slots) — selected over returning the raw `Run` aggregate (mutability leakage: `Run` exposes seven lifecycle-transition methods plus `append_manifest`), `LoadedAggregate[Run]` (same leakage plus `persisted_version` exposure), or any existing frozen type (none carries the needed shape). `next_transition_sequence` and `transition_history` are excluded as unbounded write-side/audit metadata; `manifests` is independently excluded (not by analogy to `CampaignSnapshot`, which has no equivalent field) as an unbounded, cross-package collection whose read-side representation is an unresolved question outside this milestone's authorized scope. `Run.version` — the aggregate's own domain-state field, distinct from `LoadedAggregate.persisted_version` — is also excluded, on an independently-evaluated Run-specific decision (not persistence metadata, but excluded because it numerically coincides with `persisted_version` at load time, a concrete confusability hazard the three included fields' proof obligation doesn't need to risk).

**Not-found/error behavior:** transparent propagation only, required by the already-frozen `QueryEntryPoint` contract itself, which propagates results and exceptions unchanged — no alternative (translation, nullable result, envelope) is compatible with that frozen invariant.

**Architecture-checker impact:** none. `ALLOWED["usecases"]` already grants both `"campaign"` (for the `RunLifecycleState` import) and `"run"` (for `RunRepository`, granted by M033); `FORBIDDEN_IMPORT_PREFIXES["usecases"]` already blocks persistence imports. Verified directly against live `tools/check_architecture.py` source, not asserted.

**Independent hostile design review:** found two findings. `M034-DESIGN-REVIEW-0001` (MAJOR, BLOCKING): the original design described `Run.version` — genuine aggregate domain state, advancing via lifecycle transitions and `append_manifest()` — using language belonging to `LoadedAggregate.persisted_version` (repository-loaded concurrency metadata consumed by `save()`), materially conflating the two. `M034-DESIGN-REVIEW-0002` (MINOR): the design overstated that a plain dataclass runtime-enforces its annotated field types. Decision: **M034 DESIGN REQUIRES CORRECTION.** Every other decision (capability, query identity model, handler shape, single-`get()` sequence, transparent error behavior, architecture boundary, PostgreSQL strategy) was independently verified sound.

**Correction:** `Run.version` and `persisted_version` are now distinguished precisely by name and definition everywhere in the design document; an explicit Aggregate-Version Decision independently evaluates and selects excluding `Run.version` from `RunSnapshot` on Run-specific grounds (confusability with `persisted_version`, not M031 symmetry); the persisted-version exclusion is independently justified against M032's own frozen caller-supplied `expected_persisted_version` precedent; the dataclass runtime-enforcement overstatement is corrected; manifest/history wording clarifies these are Run-owned state deliberately bounded out of scope, not irrelevant data.

**Final independent design re-review:** verified repository truth, the correction-only two-file delta, reproduction of both original findings, the correct precise distinction between `Run.version` and `persisted_version` throughout, coherent independently-justified exclusion of both from `RunSnapshot`, explicit deferral of read-to-update concurrency-token acquisition, truthful bounded header/status result semantics (`RunSnapshot` explicitly defined as bounded, not a complete Run-state representation), deliberate (not dismissive) exclusion of Run-owned `manifests`/`transition_history`, corrected dataclass runtime-type wording, preservation of every other design decision, zero architecture-checker change, checkpoint consistency, and that no MILESTONE-035 work exists. Decision: **M034 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS** (no CRITICAL or MAJOR finding). Two non-blocking observations: (1) a future implementation test should construct a `LoadedAggregate` with deliberately distinguishable `aggregate.version`/`persisted_version` values, proving neither leaks into `RunSnapshot`; (2) `RunSnapshot`'s name remains truthful under its bounded-result definition — no rename required. Both are carried forward as explicit implementation-test obligations, not redesigns. The owner formally froze the design via `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_DESIGN_FREEZE.md`.

**Status:** `APPROVED_AND_FROZEN`. Implementation has a candidate (Section 27).

**Next permitted action:** see Section 27.

## 27. MILESTONE-034 Implementation (APPROVED_AND_FROZEN)

**Implementation document:** `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_IMPLEMENTATION.md` (implementation commit `aef1ee96cf9662e6b726bdb1168fe3d79bc8a79e`).

**Delivered:** `GetRunQuery`/`RunSnapshot`/`GetRunHandler` in `empirical_platform.usecases.get_run`, exactly per the frozen design, with export-only additions to `usecases/__init__.py`. Zero `tools/check_architecture.py` change (verified: `python tools/check_architecture.py .` exit 0, checker file byte-identical to baseline).

**Tests:** 21 new tests (3 contract, 18 unit — including the two non-blocking-observation obligations the design freeze required: a deliberate `aggregate.version`/`persisted_version` distinction proof, and a manifest/transition-history exclusion proof against non-empty source data) plus 4 written PostgreSQL integration tests. Full non-integration suite: 561 passed (up from a 540-test baseline), 128 deselected, coverage 83.38% (gate 80.0%), zero regression. M031/M033/architecture regression suites re-run and passing (39 tests). `ruff`, `ruff format --check`, and canonical `mypy` (`packages = ["empirical_platform"]`) all clean. `python -m build` succeeds with `get_run.py` present in the built wheel.

**Known limitation, disclosed honestly at finalization:** the 4 PostgreSQL integration tests were written to the identical M031-established pattern and verified to import and collect cleanly, but were not executed against a live database in the original implementation session — no valid credentials were available for the native PostgreSQL service running on the host, and Docker Desktop's daemon was not running for the disposable-container pattern prior milestones used.

**Hostile self-audit:** grepped the new production module directly for every prohibited pattern (persistence imports, second `get()` call, Campaign lookup, transaction orchestration, `version`/`persisted_version`/`manifests`/`transition_history` exposure outside the docstring, composition-root/registry/dispatcher references, M035 material) — zero violations found.

**Independent hostile implementation review:** subsequently obtained Docker access and reproduced live PostgreSQL evidence, finding no CRITICAL, MAJOR, or blocking MINOR issue. Decision: **M034 IMPLEMENTATION APPROVED WITH NON-BLOCKING OBSERVATIONS.** Before freezing, the specific claimed results were independently re-verified a third time (not taken on faith): a fresh, disposable `postgres:17` container reproduced exactly 4/4 M034 PostgreSQL tests passing, 122 passed/6 skipped on the full integration regression, 561 passed on the full non-integration suite, a clean architecture-checker/ruff/mypy run, and the same pre-existing setuptools build-deprecation warning the review reported — every number matched. Three non-blocking observations (an unintended-interpreter security-script run in the original session, a stale-volume Docker Compose hiccup during review since resolved with a fresh container, and the pre-existing setuptools deprecation warning) were recorded without requiring any code change. The owner formally froze the implementation via `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_IMPLEMENTATION_FREEZE.md`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 28.

## 28. MILESTONE-035 Scope (APPROVED_AND_FROZEN)

**Scope document:** `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_SCOPE.md` (scope candidate commit `26aab1acb1d08150144b8ce52d63f17796f121ef`).

**Verified gap (evidence-driven, from-source inventory rebuild, not reused from prior tables):** of the three CQRS verbs `usecases` exercises against a repository (`add()`, `get()`, `save()`), `add()` and `get()` have each independently generalized across two aggregates (`Campaign`/`Run`, proven by M030/M033 and M031/M034 respectively), but `save()`/`OptimisticConcurrencyConflict` has been exercised exactly once — for `Campaign` only (M032) — and never for any second aggregate. This is the single largest remaining unproven-generalization gap, independently verified by a repository-wide search finding zero reference to `RunRepository.save()`, `EvidencePackageRepository.save()`, or `ReviewRepository.save()` anywhere in `src/empirical_platform/usecases/`.

**Selected scope:** Concrete Application Command Vertical Slice (Run Lifecycle Transition) — one concrete command and one concrete handler conforming to the frozen M027 `CommandHandler` Protocol, invoked through the frozen M029 `CommandEntryPoint`, transitioning an existing Run via the already-frozen `RunRepository.get()`/`save()` methods (M020) and the already-proven-once (for `Campaign`, M032) `OptimisticConcurrencyConflict` contract.

**Candidates considered and rejected:** `EvidencePackage`/`Review` creation or retrieval (each would repeat an already-twice-proven `add()`/`get()` pattern rather than close the one genuinely open verb-generalization gap, and `Review` is additionally gated two FK hops behind `EvidencePackage` readiness); retry-on-conflict policy (only one save()-based command exists — insufficient evidence to generalize responsibly, the same premature-abstraction reasoning every milestone since M030 has applied); composition-root/transport/audit-registry work (each rejected on unchanged reasoning from M030-M034 — no repeated-handler-need evidence, or an entirely disproportionate new foundational chain); a second Campaign lifecycle transition (does not close the cross-aggregate generalization gap Run lifecycle transition closes). Full sixteen-criterion comparison matrix and evidence-based rejection reasons recorded in the scope document Sections 9-11.

**Why Run over EvidencePackage/Review:** direct inspection confirms Run lifecycle transition needs zero cross-aggregate FK hop (it operates entirely within one already-existing Run row), while `EvidencePackage` creation needs one FK hop and `Review` needs two. More importantly, this project's own established discipline (M033 explicitly choosing `Run` over `EvidencePackage` for its narrower dependency distance; M034 explicitly choosing to close the `get()` gap over `EvidencePackage` creation) has consistently favored closing verb-generalization gaps over aggregate-breadth expansion when both are available — and M034's own frozen text explicitly named Run lifecycle transition as the literal next step in Run's create (M033) → read (M034) → update (M035) sequence, mirroring Campaign's own already-completed create (M030) → read (M031) → update (M032) sequence.

**Explicitly out of scope:** any second Run transition; any Run creation/retrieval change; any command or query for `EvidencePackage` or `Review`; any additional Campaign command or query; any retry/idempotency/backoff policy; any composition-root/registry/dispatcher/DI framework; any transport layer; any listing/filtering/pagination; any MILESTONE-036 work.

**Open design questions (explicitly not resolved by scope):** which of Run's seven frozen transition methods this milestone targets (mirroring M032's own scope-stage precedent of leaving the exact Campaign transition open); the exact command/handler type names and shapes; the exact result contract; the exact error-propagation mechanics; and — genuinely unresolved, not a restatement of M032's mechanism — the exact deterministic PostgreSQL conflict-scenario mechanism for Run, which has no direct analogue to `Campaign.revise_scope_statement()`.

**Independent hostile scope review:** verified repository truth, the governance-only candidate delta, the fresh architecture inventory, `Campaign` add/get/save proof, `Run` add/get proof, the absence of Run application-layer save/update proof, frozen `RunRepository.save()` support, real optimistic-concurrency enforcement, deterministic PostgreSQL conflict feasibility, one-capability scope purity, absence of any hidden transition/retry/composition/transport decision, no frozen-contract modification requirement, current architecture-permission sufficiency, independent PostgreSQL testability, and that M036 remains not started. Decision: **M035 SCOPE APPROVED WITH NON-BLOCKING OBSERVATIONS** (no CRITICAL/MAJOR/blocking MINOR finding). One non-blocking observation: this document's top-level `LATEST_FROZEN_MILESTONE` field had gone stale at `MILESTONE-028` (never updated across the M029-M034 sequence, while every detailed per-milestone section correctly and consistently showed M034 fully frozen) — corrected to `MILESTONE-034` in this same freeze; the adjacent `CHECKPOINT_CONTENT_BASELINE_*` fields were deliberately left untouched, since Section 1's own text defines them as a fixed historical-authorship anchor, not a live HEAD tracker. The owner formally froze the scope via `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_SCOPE_FREEZE.md`.

**Status:** `APPROVED_AND_FROZEN`. Design has a candidate (Section 29); implementation is not yet started.

**Next permitted action:** see Section 29.

## 29. MILESTONE-035 Design (APPROVED_AND_FROZEN)

**Design document:** `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_DESIGN.md` (design candidate commit `bac7f202c4f6dca591702d4d1404a8390c4bb755`).

**Selected transition:** `Run.authorize()` (`CREATED` → `AUTHORIZED`) — directly reachable from the state M033's frozen `CreateRunHandler` already produces, zero additional setup, optional `reason` field, mirroring M032's own selection of `Campaign.prepare_for_authorization()` as "the literal first lifecycle transition, reachable directly from the state the prior creation milestone already produces." Every other transition was rejected only for requiring additional test-setup depth, not for any domain-behavior deficiency.

**Command/handler/result contracts:** `AuthorizeRunCommand(identity, expected_persisted_version, actor, occurred_at, correlation_id=None, reason=None)`; `AuthorizeRunHandler(run_repository)` — sole dependency `RunRepository`, no `CampaignRepository`, no `Clock`; load→`authorize()`→save sequence, exactly one `get()` and one `save()`; returns `SaveResult` (already-frozen type, mirroring M032's own return contract, over raw `Run` [mutability leakage], `DomainIdentity[RunId]` [loses information], or a new type [unjustified]).

**Central load-bearing decision (expected-persisted-version model):** caller-supplied `expected_persisted_version` command field, exactly mirroring M032 — the handler must not substitute `loaded.persisted_version`, since doing so would make a genuine stale-write scenario structurally unreachable and contradict `RunRepository.save()`'s own parameter-design intent.

**Deterministic PostgreSQL conflict mechanism — independently derived, not copied from M032:** `Run` has no method analogous to `Campaign.revise_scope_statement()`; the only Run mutator that advances `AggregateVersion` while leaving `RunLifecycleState` unchanged is `Run.append_manifest()` (permitted while `CREATED`), independently confirmed by inspecting every Run method. An independently-loaded second instance calls `append_manifest()` and saves with the original `expected_persisted_version`, advancing the persisted version while leaving the persisted state at `CREATED` — so the command under test still domain-validly reaches `save()`, where the now-stale `expected_persisted_version` triggers a genuine `OptimisticConcurrencyConflict`. This deliberately avoids the exact failure mode M032's own initial design mistakenly risked (an interfering transition invalidating the command-under-test's own domain precondition before the concurrency check could be reached).

**Architecture-checker impact:** none. `ALLOWED["usecases"]` already grants `"run"`/`"shared"`; verified directly against live source.

**Hostile self-review:** performed against a sixteen-item attack list (unreachable transition, hidden predecessor transition, extra mutation/get/save, expected-version ambiguity, loaded-version substitution, aggregate/persisted-version conflation, domain failure before conflict, invalid conflict setup, hidden retry, transaction orchestration, second Run capability, EvidencePackage/Review leakage, architecture mismatch, production composition leakage, M036 leakage) — no issue survived requiring correction; independently re-verified via direct grep of the design document confirming the frozen handler code uses `command.expected_persisted_version` (never `loaded.persisted_version`) and that every `loaded.persisted_version` mention outside that code block appears only in explicitly-rejected-alternative reasoning.

**Independent hostile design review:** verified repository truth, the design-only two-file delta, `Run.authorize()` reachability from `CREATED`, the exact full-identity command model, caller-supplied `expected_persisted_version`, the exact one-`get()`/one-mutation/one-`save()` sequence, `SaveResult` return, precise aggregate/persisted-version separation, transition-history semantics, transparent error behavior, no application transaction orchestration, genuine `append_manifest()`-based PostgreSQL conflict feasibility, complete success/invalid/not-found/conflict strategies, current architecture-boundary sufficiency, no scope creep, and that M036 remains not started. Decision: **M035 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS** (no CRITICAL/MAJOR/blocking MINOR finding). One non-blocking observation: Section 28 ("Validation Ownership") overstated runtime enforcement of `DomainIdentity[RunId]` — independently verified genuine before acting (`DomainIdentity.__post_init__` checks only `isinstance(governance_id, Identifier)`, the base class, never the specific `RunId` generic parameter, since Python erases generic type parameters at runtime) — corrected in this same freeze to state precisely that `RunId` specialization is expressed statically only, with no runtime enforcement added to compensate. The owner formally froze the design via `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_DESIGN_FREEZE.md`.

**Status:** `APPROVED_AND_FROZEN`. Implementation has a candidate (Section 30).

**Next permitted action:** see Section 30.

## 30. MILESTONE-035 Implementation (APPROVED_AND_FROZEN)

**Implementation document:** `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_IMPLEMENTATION.md` (implementation commit `1037876fac376238298c22cfae0b4d5b949ffaac`).

**Delivered:** `AuthorizeRunCommand`/`AuthorizeRunHandler` in `empirical_platform.usecases.authorize_run`, exactly per the frozen design, with export-only additions to `usecases/__init__.py`. Zero `tools/check_architecture.py` change (verified: exit 0, checker file byte-identical to baseline).

**Tests:** 29 new tests (3 contract, 21 unit — including a genuine-aggregate transition-history proof, a deliberate `command.expected_persisted_version`/`loaded.persisted_version` distinction proof, and a dedicated fake-repository `OptimisticConcurrencyConflict` propagation test) plus 5 PostgreSQL integration tests. Full non-integration suite: 585 passed (up from a 561-test baseline), 133 deselected, coverage 83.49% (gate 80.0%), zero regression. M032/M033/M034/architecture regression suites re-run and passing (91 tests). `ruff`, `ruff format --check`, and canonical `mypy` all clean. `python -m build` succeeds with `authorize_run.py` present in the built wheel.

**PostgreSQL evidence — fully executed live, no disclosed limitation this time:** unlike M034's implementation session, Docker was available throughout. A fresh, disposable `postgres:17` container ran all 5 M035-specific integration tests (golden path, invalid-transition, missing-Run, deterministic conflict, no-production-composition) plus the full integration regression suite (127 passed, up from 122, 6 pre-existing skips unrelated to M035) and the full suite with PostgreSQL opt-in (712 passed, 6 skipped). The deterministic conflict scenario genuinely reproduces `OptimisticConcurrencyConflict` using the frozen `Run.append_manifest()`-based thirteen-step mechanism (an independently-loaded second Run instance advances the persisted version via a legitimate manifest append while preserving `CREATED`, so the command under test still domain-validly reaches `save()`, where the now-stale `expected_persisted_version` triggers the conflict) — independently distinct from M032's own `Campaign.revise_scope_statement()`-based mechanism, exactly as the frozen design specified. Container stopped and removed after evidence capture.

**Hostile self-audit:** grepped the new production module directly for every prohibited pattern (persistence imports, second `get()`/`save()`, `add()`/`delete()`, `loaded.persisted_version` substitution, every other Run lifecycle method, composition-root/registry/dispatcher references, `EvidencePackage`/`Review`/M036 material) — zero violations found.

**Final independent hostile implementation review:** reproduced 24 passed focused unit/contract tests, 5 passed focused M035 PostgreSQL tests, 43 passed targeted PostgreSQL regression, 127 passed full integration suite (6 skipped), 712 passed full PostgreSQL opt-in suite (6 skipped, 92.38% coverage), 585 passed non-integration suite (133 deselected, 83.49% coverage), a passing architecture checker, a passing Ruff run, a passing canonical mypy run, a passing build/wheel inspection, passing security/pip-audit, 51/51 manifest verification, byte-identical `complete.diff`, and synchronized clean repository truth. Decision: **M035 IMPLEMENTATION APPROVED WITH NON-BLOCKING OBSERVATIONS** (no CRITICAL/MAJOR/blocking MINOR finding). Three non-blocking findings, none requiring code/test/package correction: (1) secret-scan target count drift — the implementation document reported 385, independently reproducible truth is 386 (verified against the package's own evidence file and a fresh rerun during freeze; the implementation document is not rewritten, this freeze record is the authoritative corrected figure); (2) a non-canonical `mypy --explicit-package-bases` per-test-file artifact (2 unused type-ignore findings), identical to the pre-existing M031/M034 pattern, accepted as optional future test-hygiene work; (3) transient tooling friction during the reviewer's initial security-check attempts, resolved by a successful canonical rerun. The owner formally froze the implementation via `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_IMPLEMENTATION_FREEZE.md`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 31.

## 31. Macro Milestone Protocol (Active from MILESTONE-036)

Effective from MILESTONE-036 onward: `MACRO_MILESTONE_PROTOCOL_ACTIVE_FROM=MILESTONE-036`. One Complete Macro Milestone Mission (scope through push, including governance, tests, PostgreSQL evidence, and the external-review package) is followed by one Complete Independent Hostile Milestone Review; if correction is required, one narrow correction mission and one final re-review; Owner Freeze is then recorded, normally at the start of the next milestone's mission. This is a workflow consolidation only — it does not reduce repository-truth verification, independent review, live PostgreSQL evidence, architecture validation, external-review package requirements, manifest/ZIP integrity verification, or owner freeze authority; every gate M030-M035 required remains required for M036 onward. Full detail: `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_IMPLEMENTATION_FREEZE.md` Section 49.

**Next permitted action:** see Section 32.

## 32. MILESTONE-036 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_036_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CREATION_SCOPE.md`, `..._DESIGN.md`, `..._IMPLEMENTATION.md` (implementation commit `4672cfc7137e19aa628ebe996883e10a1d3f90c3`).

**Fresh architecture inventory:** all three CQRS verbs (`add()`, `get()`, `save()`) are now independently proven across two aggregates each (Campaign, Run) — the pattern-generalization question this project closed one verb at a time since M033 is fully answered. `EvidencePackage` and `Review` remain the only aggregates with zero application-layer proof — verified by a repository-wide search finding no reference to either anywhere in `src/empirical_platform/usecases/` (6 modules total, none touching `evidence`/`review`).

**Selected scope:** one concrete command creating a new `EvidencePackage` for an existing `Run`, via `EvidencePackageRepository.add()`. Selected over a second Run transition (repeats an already-twice-proven `save()` pattern), retry policy (still no evidenced concrete need despite two data points), `EvidencePackage`/`Review` retrieval (cannot precede creation / gated two FK hops behind), and composition-root work (no repeated-handler-need evidence). `EvidencePackage`'s constructor (`identity`, `run_id`) mirrors `Run`'s pre-M033 shape exactly; the real `evidence_package.run_id → run.governance_id` FK mirrors `run.campaign_id → campaign.governance_id` exactly — the identical mechanism M033 already proved, independently re-verified against `EvidencePackage`'s own adapter code (not assumed by analogy).

**Design:** identity model — caller-supplied raw governance-ID string + handler-generated runtime ID (mirrors `CreateRunCommand`, independently justified for a creation command with nothing yet to reference via full `DomainIdentity`). Run-existence — persistence-enforced via the real FK only, no `RunRepository` dependency (mirrors M033's Campaign-existence mechanism, independently re-confirmed against live adapter source: FK violations are SQLSTATE `23503`, not classified as unique violations, reaching a bare unmodified `FoundationError` re-raise). Result — `DomainIdentity[EvidencePackageId]` (mirrors `CreateRunHandler`'s return; independently justified as correct for creation vs. M032/M035's `SaveResult` for transitions).

**Architecture impact:** exactly one narrow addition (`"evidence"` to `ALLOWED["usecases"]`), verified live. Required fixture maintenance: removed the now-obsolete `usecases/bad_evidence_import.py` (would silently stop triggering); added `usecases/bad_review_import.py` (usecases still cannot import review) and `evidence/bad_usecases_import.py` (new reverse-direction evidence, mirroring the `run`/`campaign` precedent).

**Tests:** 23 new (3 contract, 15 unit, 5 PostgreSQL integration — all executed live against a fresh disposable container, including the FK-violation scenario). Full non-integration suite: 603 passed (up from 585), 138 deselected, coverage 83.58%, zero regression. Full integration regression: 132 passed (up from 127). Full suite with PostgreSQL: 735 passed, 92.74% coverage.

**Hostile self-audit:** zero genuine prohibited-pattern matches in the new production module (three docstring "for" false positives only); no `RunRepository` dependency; no `EvidencePackage` mutation method referenced; no `Review`/M037 material anywhere.

**Independent hostile macro review:** covered scope, design, implementation, tests, evidence, and the external-review package as one consolidated review, per the active Macro Milestone Protocol (Section 31). Decision: **M036 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — no CRITICAL/MAJOR/blocking MINOR finding. Three non-blocking observations, none requiring code/test/package correction: (1) M036-OBS-0001 — the implementation commit's title reads "Run authorization usecase" (a copy-paste artifact from the M035 commit template) instead of "EvidencePackage creation usecase"; content and lineage are correct (`git show --stat 4672cfc7` touches only `EvidencePackage`-related files); git history is not amended, per this project's standing no-history-rewrite discipline. (2) M036-OBS-0002 — one initial non-canonical security invocation used system Python 3.14; the canonical `.venv` rerun passed; no correction required. (3) M036-OBS-0003 — a pre-existing `setuptools` license-table deprecation warning during `python -m build`, identical to the one already documented in M034's own freeze record; recorded only, no packaging change unless MILESTONE-037 independently requires one.

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31). Owner Freeze record: `MILESTONE_036_EVIDENCE_PACKAGE_CREATION_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 33.

## 33. MILESTONE-036 Owner Freeze

**Owner Freeze record:** `MILESTONE_036_EVIDENCE_PACKAGE_CREATION_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-036 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the independent hostile macro review recorded in Section 32.

**Delivered capability, frozen:** creation of a new `EvidencePackage` for an existing `Run`, via `CreateEvidencePackageCommand`/`CreateEvidencePackageHandler` (`src/empirical_platform/usecases/create_evidence_package.py`), exactly per Section 32. No `EvidencePackage` retrieval, mutation, `Review` work, retry policy, or composition-root work is authorized by this freeze.

**Freeze declaration:** `M036 MACRO MILESTONE APPROVED_AND_FROZEN`. `M036 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 34.

## 34. MILESTONE-037 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_037_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh architecture inventory:** `EvidencePackage` has one proven verb (`add()`, M036); `get()` and `save()` remain unproven for it, and all three verbs remain unproven for `Review`. Verified live: `grep -rl "evidence" src/empirical_platform/usecases/*.py` matches only `create_evidence_package.py`; `grep -rl "review" src/empirical_platform/usecases/*.py` matches nothing. `EvidencePackageRepository.get()` is already implemented and frozen at the adapter level (M023).

**Selected scope:** one concrete query retrieving an existing `EvidencePackage` by full identity, via `EvidencePackageRepository.get()`, returning a bounded `EvidencePackageSnapshot`. Selected over EvidencePackage lifecycle transition/`save()` (lower marginal generalization value — the `save()`+`OptimisticConcurrencyConflict` pattern is already proven twice, M032/M035), Review creation (FK-viable per a live-verified `review.target_evidence_package_id -> evidence_package.governance_id` foreign key, but would break the project's own twice-repeated per-aggregate create-retrieve-transition completion cadence: Campaign M030-M032, then Run M033-M035, only then EvidencePackage M036 onward), Review retrieval (depends on Review creation existing first), retry policy (still no evidenced concrete need), and composition-root work (no repeated-handler-need evidence). Full candidate comparison: scope document Section 7.

**Design:** query identity — caller-supplied full `DomainIdentity[EvidencePackageId]` (mirrors `GetRunQuery`/`GetCampaignQuery`; a governance-ID-only lookup was rejected since it would require altering the frozen M020 repository Protocol). Result — `EvidencePackageSnapshot(identity, run_id, state)`, deliberately excluding `version`/`persisted_version`/`criterion_results`/`artifact_references`/`transition_history`, mirroring `RunSnapshot`'s own established exclusions.

**Architecture impact:** none. `usecases` already had `evidence` in `ALLOWED["usecases"]` since M036; this read-only query uses an already-permitted import edge. `tools/check_architecture.py` unchanged (verified via `git diff`); `python tools/check_architecture.py .` exit 0.

**Tests:** 25 new (3 contract, 18 unit, 4 PostgreSQL integration — all executed live against a fresh disposable container, including the not-found scenario and a criterion-result/artifact-reference/transition-history eager-load regression). Full non-integration suite: 624 passed (up from 603), 142 deselected, coverage 83.68%, zero regression. Full integration regression: 136 passed (up from 132). Full suite with PostgreSQL: 760 passed, 92.78% coverage.

**Hostile self-audit:** zero genuine prohibited-pattern matches in the new production module (one docstring "for one" false positive only, mirroring M036's own precedent); no `add()`/`save()`/mutation-method call of any kind; no `Review`/`RunRepository`/`CampaignRepository`/M038 material anywhere; exactly one `get()` call.

**Independent hostile macro review:** covered scope, design, implementation, tests, evidence, and the external-review package as one consolidated review, per the active Macro Milestone Protocol (Section 31). Decision: **M037 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — no CRITICAL/MAJOR/blocking MINOR finding. Four non-blocking observations, all resolved in the owner freeze record without any code, test, or package correction: (1) M037-OBS-0001 — the implementation document's summary line miscounted the test total as 24 instead of the correct 25 (18 unit + 3 contract + 4 integration), independently re-verified by fresh collection at freeze time; (2) M037-OBS-0002 — the M037-specific PostgreSQL "eager-load regression" test only proves empty-collection loading, not non-empty owned-collection reconstruction, which is separately and already proven by the pre-existing M023 repository regression suite; (3) M037-OBS-0003 — secret-scan target counts recorded as time-scoped values (402 at evidence-capture time, 403 independently reproduced twice at freeze time); a cited final-review figure of 411 could not be independently reproduced during the freeze session and is recorded as an unreconciled, non-blocking discrepancy — security passed under every count; (4) M037-OBS-0004 — the same pre-existing `setuptools` license-table deprecation warning already documented in M034/M036, recorded only.

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31). Owner Freeze record: `MILESTONE_037_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 35.

## 35. MILESTONE-037 Owner Freeze

**Owner Freeze record:** `MILESTONE_037_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-037 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the independent hostile macro review recorded in Section 34.

**Delivered capability, frozen:** retrieval of an existing `EvidencePackage` by full identity, via `GetEvidencePackageQuery`/`GetEvidencePackageHandler` (`src/empirical_platform/usecases/get_evidence_package.py`), returning a bounded `EvidencePackageSnapshot`, exactly per Section 34. No `EvidencePackage` mutation/`save()`, `Review` work, retry policy, or composition-root work is authorized by this freeze.

**Freeze declaration:** `M037 MACRO MILESTONE APPROVED_AND_FROZEN`. `M037 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 36.

## 36. MILESTONE-038 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_038_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh architecture inventory:** `EvidencePackage` has two proven verbs (`add()` M036, `get()` M037); `save()`/`OptimisticConcurrencyConflict` remains proven for Campaign (M032) and Run (M035) only — the single largest remaining unproven-generalization gap. `EvidencePackageRepository.save()`/`PostgresEvidencePackageRepository.save()` were already implemented and frozen at M020/M023.

**Selected scope:** one concrete command transitioning an existing `EvidencePackage` from `INITIALIZED` to `COLLECTING` via `EvidencePackage.start_collection()`. Selected over EvidencePackage criterion-result/artifact mutation (gated behind this milestone — not reachable via any frozen application command yet), Review creation (heavier design surface, defers per the same twice-repeated per-aggregate cadence argument M037 used), Review retrieval (depends on Review creation), retry policy (still no evidenced concrete need), and composition-root work (no repeated-handler-need evidence). Full candidate comparison: scope document Section 8.

**Design — independently derived conflict mechanism (not copied from M032/M035):** a fresh inventory of `EvidencePackage`'s aggregate methods found **no non-transition mutation available while `INITIALIZED`** — unlike `Campaign.revise_scope_statement()` (available in `DRAFT`) and `Run.append_manifest()` (available in `CREATED`), `start_collection()` is the only method operating on `INITIALIZED`. Two independently loaded callers racing the same transition therefore produce a domain-level `ValueError` (the second caller's own `start_collection()` call is invalid once the first has advanced the durable state to `COLLECTING`), never a repository-level `OptimisticConcurrencyConflict` — disclosed as a genuine, scope-appropriate boundary of this specific transition (design Sections 6/20), independently reproduced live against real PostgreSQL. `OptimisticConcurrencyConflict` propagation itself remains fully proven at the unit level via a fake repository unconstrained by the aggregate's own state machine.

**Architecture impact:** none. `usecases` already had `evidence` in `ALLOWED["usecases"]` since M036. `tools/check_architecture.py` unchanged (verified via `git diff`); `python tools/check_architecture.py .` exit 0.

**Tests:** 28 new (3 contract, 21 unit, 4 PostgreSQL integration — all executed live against a fresh disposable container, including the two-racing-callers scenario). Full non-integration suite: 648 passed (up from 624), 146 deselected, coverage 83.79%, zero regression. Full integration regression: 140 passed (up from 136). Full suite with PostgreSQL: 788 passed, 92.83% coverage.

**Hostile self-audit:** zero genuine prohibited-pattern matches in the new production module (two docstring "for" false positives only); no `add()` call; no `add_criterion_result`/`add_artifact_reference`/`seal`/`invalidate` call; no `Review`/M039 material anywhere; exactly one `get()` and one `save()` call.

**Independent hostile macro review:** covered scope, design, implementation, tests, evidence, and the external-review package as one consolidated review, per the active Macro Milestone Protocol (Section 31). Decision: **M038 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — no CRITICAL/MAJOR/blocking MINOR finding. Two non-blocking findings, both resolved in the owner freeze record without any code, test, or package correction: (1) M038-REVIEW-0001 — secret-scan target counts recorded as time-scoped values (410 at implementation-evidence-capture time, 412 independently reproduced at owner-freeze time, 413 cited by the independent review); security passed under every count; (2) M038-REVIEW-0002 — the same pre-existing `setuptools` license-table deprecation warning already documented in M034/M036/M037, recorded only. The review's own specific evidence citations (an 89-test focused command, a 53-test predecessor-plus-M038 PostgreSQL regression) were independently reproduced exactly during the freeze, confirming the review as genuine and reproducible.

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31). Owner Freeze record: `MILESTONE_038_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 37.

## 37. MILESTONE-038 Owner Freeze

**Owner Freeze record:** `MILESTONE_038_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-038 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the independent hostile macro review recorded in Section 36.

**Delivered capability, frozen:** transition of an existing `EvidencePackage` from `INITIALIZED` to `COLLECTING`, via `StartEvidencePackageCollectionCommand`/`StartEvidencePackageCollectionHandler` (`src/empirical_platform/usecases/start_evidence_package_collection.py`), completing `EvidencePackage`'s create-retrieve-transition trio (M036/M037/M038), exactly per Section 36. No `add_criterion_result`/`add_artifact_reference`/`seal`/`invalidate`, `Review` work, retry policy, or composition-root work is authorized by this freeze.

**Frozen concurrency model:** two independently loaded callers racing `start_collection()` produce a domain-level `ValueError` for the second (later) caller, never a repository-level `OptimisticConcurrencyConflict` — an independently derived, permanently disclosed boundary of this specific transition (freeze record Sections 32-33), since `EvidencePackage` has no non-transition mutation available while `INITIALIZED`, unlike `Campaign`/`Run`.

**Freeze declaration:** `M038 MACRO MILESTONE APPROVED_AND_FROZEN`. `M038 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 38.

## 38. MILESTONE-039 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_039_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh architecture inventory:** `EvidencePackage`'s create-retrieve-transition trio (`add()`/`get()`/`save()`-via-`start_collection()`) closed at M038. Two gaps remained: the owned-collection-append write pattern (never proven anywhere in this project) and `Review` (zero application-layer proof). `EvidencePackage.state == COLLECTING` became reachable via a frozen application command for the first time at M038, unlocking `add_criterion_result()`/`add_artifact_reference()`.

**Selected scope:** one concrete command recording a `CriterionResult` on an existing, `COLLECTING` `EvidencePackage`. Review creation was seriously evaluated (now FK-viable, and arguably no longer blocked by the trio-completion cadence M037/M038 used) but deferred: it would repeat an already-three-times-proven create/retrieve/transition CQRS pattern rather than close the still-open owned-collection-append gap, and semantically a Review against a package that cannot yet be `SEALED` does not reflect the real business flow. Full candidate comparison: scope document Section 8.

**Design — closes the M038-disclosed conflict-evidence gap:** unlike `start_collection()` (no non-transition interfering write available while `INITIALIZED`), `add_criterion_result()` operates on `COLLECTING`, which has a genuine sibling method (`add_artifact_reference()`) usable as a state-preserving, version-advancing interfering write — enabling, for the first time since M038's own disclosed boundary, a **genuine** `OptimisticConcurrencyConflict` reproduction against real PostgreSQL through the natural application call sequence. `evidence_package_id` on the constructed `CriterionResult` is derived from the loaded aggregate's own identity, never a separately supplied (and therefore potentially mismatched) command field.

**Architecture impact:** none. `usecases` already had `evidence` in `ALLOWED["usecases"]` since M036. `tools/check_architecture.py` unchanged; `python tools/check_architecture.py .` exit 0.

**Tests:** 32 new (3 contract, 23 unit, 6 PostgreSQL integration — all executed live against a fresh disposable container, including the genuine deterministic conflict scenario). Full non-integration suite: 674 passed (up from 648), 152 deselected, coverage 83.91%, zero regression. Full integration regression: 146 passed (up from 140). Full suite with PostgreSQL: 820 passed, 92.88% coverage.

**Hostile self-audit:** zero genuine prohibited-pattern matches in the new production module (one docstring "for" false positive only); no `add()` call; no `add_artifact_reference`/`seal`/`invalidate`/`start_collection` call; no `Review`/M040 material anywhere; exactly one `get()` and one `save()` call.

**Independent hostile macro review:** covered scope, design, implementation, tests, evidence, and the external-review package as one consolidated review, per the active Macro Milestone Protocol (Section 31). Decision: **M039 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — no CRITICAL/MAJOR/blocking MINOR finding. Two non-blocking observations, both resolved in the owner freeze record without any code, test, or package correction: (1) M039-OBS-0001 — the same pre-existing `setuptools` license-table deprecation warning already documented in M034/M036/M037/M038; (2) M039-OBS-0002 — a stale local PostgreSQL volume password affected only an initial non-canonical reviewer setup attempt, resolved by isolated clean PostgreSQL verification. A further discrepancy independently found during freeze verification (the review's own cited "65 passed" targeted regression figure could not be exactly reproduced with any tested command grouping, though the closest tested groupings — 59 and 68 passed — both show zero regression) is recorded transparently in the freeze record rather than asserted as fact.

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31). Owner Freeze record: `MILESTONE_039_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 39.

## 39. MILESTONE-039 Owner Freeze

**Owner Freeze record:** `MILESTONE_039_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-039 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the independent hostile macro review recorded in Section 38.

**Delivered capability, frozen:** recording of a `CriterionResult` on an existing, `COLLECTING` `EvidencePackage`, via `RecordEvidencePackageCriterionResultCommand`/`RecordEvidencePackageCriterionResultHandler` (`src/empirical_platform/usecases/record_evidence_package_criterion_result.py`), with `evidence_package_id` derived from the loaded aggregate's own identity, exactly per Section 38. No `add_artifact_reference`/`seal`/`invalidate`/`start_collection`, `Review` work, retry policy, or composition-root work is authorized by this freeze.

**Frozen real-conflict model:** a genuine `OptimisticConcurrencyConflict` reproduction against real PostgreSQL, using an independently loaded second instance calling `add_artifact_reference()` (a legitimate, state-preserving domain method) as the interfering write — closing the boundary M038's own freeze record explicitly disclosed as unavailable for `start_collection()` (freeze record Sections 36-37). No direct SQL fabrication, no patched aggregate internals, no invalid row, no second production command.

**Freeze declaration:** `M039 MACRO MILESTONE APPROVED_AND_FROZEN`. `M039 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 40.

## 40. MILESTONE-040 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_040_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh architecture inventory:** `EvidencePackage`'s owned-collection-append vocabulary had `add_criterion_result` proven (M039) but `add_artifact_reference` unproven. `seal()`'s own precondition requires both collections non-empty; since no frozen command could produce a non-empty `artifact_references` collection, `seal()` was found not independently reachable this milestone without a scaffolding compromise (the first time in this project's history that a candidate was excluded for this specific reason).

**Selected scope:** one concrete command recording an `ArtifactReference` on an existing, `COLLECTING` `EvidencePackage`. Review creation was again evaluated and again rejected — explicitly not merely because its FK exists, but because `EvidencePackage`'s own owned-collection vocabulary remained incomplete and the real-world review-of-completed-evidence semantics still could not be reached. Full candidate comparison: scope document Section 7.

**Design — simplest command of any milestone to date:** `ArtifactReference` carries no `evidence_package_id` field at all, so the ownership-derivation question M039 had to resolve does not arise here — the command has exactly three fields. The deterministic conflict mechanism is the exact reverse pairing of M039's own: `add_criterion_result()` (now a frozen, real production capability) serves as the interfering write, again producing a **genuine** `OptimisticConcurrencyConflict` against real PostgreSQL through the natural application call sequence.

**Architecture impact:** none. `usecases` already had `evidence` in `ALLOWED["usecases"]` since M036. `tools/check_architecture.py` unchanged; `python tools/check_architecture.py .` exit 0.

**Tests:** 31 new (3 contract, 22 unit, 6 PostgreSQL integration — all executed live against a fresh disposable container, including the genuine deterministic conflict scenario). Full non-integration suite: 699 passed (up from 674), 158 deselected, coverage 84.00%, zero regression. Full integration regression: 152 passed (up from 146). Full suite with PostgreSQL: 851 passed, 92.92% coverage.

**Hostile self-audit:** zero genuine prohibited-pattern matches in the new production module (one docstring "for" false positive only); no `add()` call; no `add_criterion_result`/`seal`/`invalidate`/`start_collection` call; no `Review`/M041 material anywhere; exactly one `get()` and one `save()` call.

**Independent hostile macro review:** covered scope, design, implementation, tests, evidence, and the external-review package as one consolidated review, per the active Macro Milestone Protocol (Section 31). Decision: **M040 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — no CRITICAL/MAJOR/blocking MINOR finding. One non-blocking observation, resolved in the owner freeze record without any code, test, or package correction: M040-OBS-0001 — the same pre-existing `setuptools` license-table deprecation warning already documented in M034/M036/M037/M038/M039. The review's own cited "74 passed" targeted regression figure (M023 combined with the full M030-M040 vertical-slice suite run) was independently reproduced exactly during the freeze.

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31). Owner Freeze record: `MILESTONE_040_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 41.

## 41. MILESTONE-040 Owner Freeze

**Owner Freeze record:** `MILESTONE_040_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-040 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the independent hostile macro review recorded in Section 40.

**Delivered capability, frozen:** recording of an `ArtifactReference` on an existing, `COLLECTING` `EvidencePackage`, via `RecordEvidencePackageArtifactReferenceCommand`/`RecordEvidencePackageArtifactReferenceHandler` (`src/empirical_platform/usecases/record_evidence_package_artifact_reference.py`), exactly per Section 40. `EvidencePackage`'s owned-collection-append vocabulary is now complete (both `add_criterion_result` and `add_artifact_reference` proven). No `seal`/`invalidate`, `Review` work, retry policy, or composition-root work is authorized by this freeze.

**Frozen real-conflict model:** a genuine `OptimisticConcurrencyConflict` reproduction against real PostgreSQL, using an independently loaded second instance calling `add_criterion_result()` (a legitimate, state-preserving, now-frozen production capability) as the interfering write — the exact reverse pairing of M039's own mechanism (freeze record Sections 36-37). No direct SQL fabrication, no patched aggregate internals, no invalid row, no second production command.

**Freeze declaration:** `M040 MACRO MILESTONE APPROVED_AND_FROZEN`. `M040 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 42.

## 42. MILESTONE-041 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_041_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_SEALING_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh architecture inventory:** `EvidencePackage`'s owned-collection-append vocabulary completed at M040 (both `add_criterion_result` and `add_artifact_reference` proven). `seal()` requires both collections non-empty plus `COLLECTING` state — for the first time in this lineage, every one of a candidate's own preconditions is satisfiable exclusively via frozen application commands (M036 → M038 → M039 → M040 → `seal()`), with no scaffolding bypass required.

**Selected scope:** one concrete command transitioning an existing, `COLLECTING` `EvidencePackage` (with both collections non-empty) to `SEALED`. Review creation was evaluated a **fourth** time and again deferred — not because its FK is unreachable, but because sealing first means a future Review-creation milestone can target a genuinely completed package, matching real-world semantics this project's domain models imply. Full candidate comparison: scope document Section 8.

**Design:** command shape identical to `StartEvidencePackageCollectionCommand` (M038). Uniquely, this transition introduces **three** independently distinguishable domain-`ValueError` scenarios (empty criterion results, empty artifact references, invalid state) rather than the single-precondition failure every prior transition (M032, M035, M038) exercised — each independently tested at both unit and PostgreSQL integration level. Deterministic conflict mechanism: `add_artifact_reference()` (frozen since M040) used as the interfering write, producing a genuine `OptimisticConcurrencyConflict`.

**Architecture impact:** none. `usecases` already had `evidence` in `ALLOWED["usecases"]` since M036. `tools/check_architecture.py` unchanged; `python tools/check_architecture.py .` exit 0.

**Tests:** 34 new (3 contract, 24 unit, 7 PostgreSQL integration — the largest integration surface of any EvidencePackage milestone to date, proportional to the transition's three-part precondition, all executed live against a fresh disposable container including the genuine deterministic conflict scenario). Full non-integration suite: 726 passed (up from 699), 165 deselected, coverage 84.10%, zero regression. Full integration regression: 159 passed (up from 152). Full suite with PostgreSQL: 885 passed, 92.97% coverage.

**Hostile self-audit:** zero genuine prohibited-pattern matches in the new production module (one docstring "for" false positive only); no `add()` call; no `add_criterion_result`/`add_artifact_reference`/`invalidate`/`start_collection` call; no `Review`/M042 material anywhere; exactly one `get()` and one `save()` call.

**Correction lineage:** a post-implementation hostile author self-review found one confirmed, minor, documentation-only defect (M041-SELFREVIEW-0001) — Design Section 18 misstated `seal()`'s precondition-check order, claiming an `INITIALIZED` package would fail on the state check first when in fact the two collection-precondition checks execute before the state check. Corrected via commit `556b21263182eed229b6528b37c4fa2c4d1e69d6`, hash-recorded via `a7ae5e25f2305e6aa88410c1917443a20b9f3ae6`; no source, test, or contract changed. The external-review package was refreshed against the corrected HEAD (new ZIP SHA-256 `c38fbbb24edbcc56314b039c8bcdf9eae37c4956bc11fe32bacdd1071e126846`).

**Independent hostile macro review (post-correction):** covered scope, design, implementation, tests, evidence, and the refreshed external-review package as one consolidated review, per the active Macro Milestone Protocol (Section 31). Decision: **M041 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — no CRITICAL/MAJOR/blocking MINOR finding. The review went beyond rerunning the existing test suite: it independently wrote and ran a standalone script bypassing the repository/ORM layer entirely, querying PostgreSQL with raw SQL, to confirm the interfering write, the genuinely-failed `seal()` attempt, the genuine `OptimisticConcurrencyConflict` (not a domain `ValueError`), and the exact transition-history state — all directly, not via the test framework's own assertions. One non-blocking observation: `M041_FINALIZATION_COMMIT=PENDING` at review time, confirmed consistent with the identical M038/M039/M040 pattern (resolved only at each milestone's own Owner Freeze).

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31), including the tracked design-wording correction. Owner Freeze record: `MILESTONE_041_EVIDENCE_PACKAGE_SEALING_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 43.

## 43. MILESTONE-041 Owner Freeze

**Owner Freeze record:** `MILESTONE_041_EVIDENCE_PACKAGE_SEALING_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-041 scope, design, and implementation (as corrected) as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the independent hostile macro review recorded in Section 42.

**Delivered capability, frozen:** transition of an existing, `COLLECTING` `EvidencePackage` (with both owned collections non-empty) to `SEALED`, via `SealEvidencePackageCommand`/`SealEvidencePackageHandler` (`src/empirical_platform/usecases/seal_evidence_package.py`), completing `EvidencePackage`'s lifecycle-completion transition, exactly per Section 42. No `invalidate`, `Review` work, retry policy, or composition-root work is authorized by this freeze.

**Frozen conflict model:** a genuine `OptimisticConcurrencyConflict` reproduction against real PostgreSQL, independently re-confirmed via direct SQL bypassing the ORM/test-framework layers, using `add_artifact_reference()` (frozen since M040) as the interfering write (freeze record Section 21). No direct SQL fabrication, no patched aggregate internals, no invalid row, no second production command.

**Freeze declaration:** `M041 MACRO MILESTONE APPROVED_AND_FROZEN`. `M041 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 44.

## 44. MILESTONE-042 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_042_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_CREATION_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh, complete architecture inventory:** a from-scratch inventory (not assumed from any prior milestone's conclusions) found `Review` the only aggregate in the entire domain model with zero application-layer proof of any verb — `Campaign`/`Run`/`EvidencePackage` all have full create/retrieve/transition/owned-collection-append proof with genuine conflict evidence. `ReviewRepository`, `PostgresReviewRepository`, and `ConcreteReviewMapper` were all already frozen (M020/M021/M023) with zero infrastructure gap.

**Selected scope:** one concrete command creating a new `Review` targeting an existing `EvidencePackage`, via `ReviewRepository.add()` — the third proof of the `add()`-with-real-FK pattern (after M033, M036). Four prior scope documents (M037/M039/M040/M041) had each independently deferred Review creation, every time explicitly pending `EvidencePackage` reaching a genuinely `SEALED` state via frozen commands — a condition M041 satisfied. `EvidencePackage.invalidate()` was seriously evaluated and rejected as lower-leverage (repeating an already-four-times-proven single-precondition-transition pattern on a fully-proven aggregate, versus closing the one aggregate with zero proof of anything). Full candidate comparison: scope document Section 8.

**Design:** a three-field command (`review_governance_id`, `target_evidence_package_governance_id`, `reviewer_reference`), mirroring `CreateEvidencePackageCommand`'s shape plus one additional plain-string field. Target existence enforced entirely by the real `review.target_evidence_package_id → evidence_package.governance_id` foreign key, no `EvidencePackageRepository` dependency — independently re-verified against live adapter source, not assumed by analogy.

**Architecture impact:** exactly one narrow addition (`"review"` to `ALLOWED["usecases"]`), with corresponding fixture maintenance (removed the now-obsolete `usecases/bad_review_import.py`; added `review/bad_usecases_import.py`, closing the one remaining gap in the reverse-direction fixture set already established for `campaign`/`run`/`evidence`).

**Tests:** 24 new (3 contract, 16 unit, 5 PostgreSQL integration, all executed live against a fresh disposable container). Full non-integration suite: 745 passed (up from 726), 170 deselected, coverage 84.20%, zero regression. Full integration regression: 164 passed (up from 159). Full suite with PostgreSQL: 909 passed, 93.06% coverage.

**Hostile self-audit:** static grep sweep found zero genuine prohibited-pattern matches. Beyond static review, a direct-SQL adversarial verification script — bypassing the ORM/repository layer entirely, mirroring M041's independent-review technique — confirmed genuinely, via raw SQL row inspection: Review creation succeeds against a deliberately non-`SEALED` (`INITIALIZED`) target with no hidden state dependency (only the documented FK-only constraint applies); duplicate governance-ID and missing-target both behave exactly as designed with zero spurious rows persisted. Full transcript in the external-review package.

**Independent hostile macro review:** a 27-phase independent review, treating every source file, test, governance document, and packaged claim as potentially wrong, independently re-derived repository truth, the domain contract (fresh full read of `review/aggregate.py` confirming zero target-state reference), the schema/FK constraints, the command/handler contracts (prohibited-pattern grep, zero matches), all test counts against a freshly self-provisioned PostgreSQL container, the architecture-checker diff and fixture maintenance, and the external-review ZIP SHA-256 — and independently wrote and ran its own direct-SQL adversarial script, separate from the implementation session's own, reproducing identical results with zero contradiction. Decision: **M042 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS.** Two non-blocking observations raised: M042-REVIEW-0001 (the review mission's own stated "9 files" premise did not match the actual, correct 13-file delta) and M042-REVIEW-0002 (the packaged evidence recorded 442 secret-scan targets against an independently reproduced 443; the scan itself found zero findings under either count).

**Validation-completion mission:** a subsequent narrow, read-only mission independently rebuilt the sdist/wheel, inspected full contents (`create_review.py` present; tests/external-review/cache/pyc excluded), smoke-imported both frozen symbols, ran `scripts/security.ps1` and `scripts/verify.ps1` end-to-end (the latter's own negative architecture-fixture step independently re-confirming the fixture-maintenance claim via a distinct mechanism), ran `pip-audit` standalone, reproduced the secret-scan count (443, confirming M042-REVIEW-0002 as a genuine, non-blocking, zero-security-impact drift), and reconfirmed the external-review ZIP SHA-256 byte-for-byte. Decision unchanged: **APPROVED WITH NON-BLOCKING OBSERVATIONS.**

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31). Owner Freeze record: `MILESTONE_042_REVIEW_CREATION_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 45.

## 45. MILESTONE-042 Owner Freeze

**Owner Freeze record:** `MILESTONE_042_REVIEW_CREATION_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-042 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the independent hostile macro review and the subsequent validation-completion mission recorded in Section 44.

**Delivered capability, frozen:** creation of a new `Review` targeting an existing `EvidencePackage` by governance ID, via `CreateReviewCommand`/`CreateReviewHandler` (`src/empirical_platform/usecases/create_review.py`) — the third proof of the `add()`-with-real-FK pattern, closing the last aggregate with zero prior application-layer proof. No `Review` retrieval, lifecycle transition, or `EvidencePackage.invalidate()` work is authorized by this freeze.

**Frozen referential-integrity model:** target existence enforced entirely by the real PostgreSQL foreign key `review.target_evidence_package_id -> evidence_package.governance_id`; no application-level pre-check; no target-state requirement of any kind, independently confirmed twice via two separately authored direct-SQL adversarial scripts against separately provisioned containers (freeze record Sections 23-26, 40).

**Freeze declaration:** `M042 MACRO MILESTONE APPROVED_AND_FROZEN`. `M042 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 46.

## 46. MILESTONE-043 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_043_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_REVIEW_RETRIEVAL_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh, complete architecture inventory:** a from-scratch inventory of all 13 `usecases` modules found `Review` the only aggregate in the domain model with zero query-side (`QueryHandler`) proof of any kind — `Campaign`/`Run`/`EvidencePackage` each already have both a frozen `add`/`create` command and a frozen `get`/retrieve query; `Review` had only M042's `add`. `ReviewRepository.get()` and `PostgresReviewRepository.get()` were both already frozen (M020/M023) with zero infrastructure gap.

**Selected scope:** one concrete query retrieving an existing `Review` by full identity, via `ReviewRepository.get()` — the fourth proof of the `get()`-retrieval pattern (after M031 Campaign, M034 Run, M037 EvidencePackage). `Review`'s first lifecycle transition (`start()`), finding recording (`add_finding()`), and completion (`complete()`) were each evaluated and rejected: `start()` would be a fifth instance of an already four-times-proven single-precondition-transition pattern; `add_finding()` and `complete()` each have an unmet sequencing prerequisite (`add_finding()` requires `start()` first; `complete()` requires both `start()` and `add_finding()` first), making either selection alone either incomplete or a multi-capability violation of "one capability only." Full candidate comparison: scope document Section 8.

**Design:** a one-field query (`identity`), mirroring `GetEvidencePackageQuery`'s shape exactly. Result contract `ReviewSnapshot` (four fields: `identity`, `target_evidence_package_id`, `reviewer_reference`, `state`) mirrors `EvidencePackageSnapshot`'s deliberately bounded shape, excluding `findings`, `transition_history`, `version`, `persisted_version`, `disposition`, `final_disposition_rationale`, and `cancellation_reason`.

**Architecture impact:** none. `usecases` already had `review` in `ALLOWED["usecases"]` since M042. `tools/check_architecture.py` unchanged; `python tools/check_architecture.py .` exit 0.

**Tests:** 25 new (3 contract, 18 unit, 4 PostgreSQL integration, all executed live against a fresh disposable container). Full non-integration suite: 766 passed (up from 745), 174 deselected, coverage 84.29%, zero regression. Full integration regression: 168 passed (up from 164). Full suite with PostgreSQL: 934 passed, 93.10% coverage.

**Hostile self-audit:** targeted prohibited-pattern grep on `get_review.py` found zero genuine matches; the `usecases/__init__.py` diff is purely additive; a full scope-creep sweep across the diff found only test-fixture-internal `Review.start()`/`add_finding()`/`complete()` calls used exclusively to prove those fields are excluded from `ReviewSnapshot`, not a production capability.

**Independent hostile macro review:** a 19-phase independent review, treating every source file, test, governance document, commit message, and packaged claim as potentially wrong, independently re-derived repository truth, a fresh architecture inventory, a full production-code read (zero prohibited patterns), a freshly written adversarial script proving zero snapshot field leakage against a fully populated `Review`, object-identity (`is`) verification of identity pass-through and exception propagation, all test counts against a self-provisioned PostgreSQL container, and a second independently written direct-SQL adversarial script confirming raw persisted state (2 findings, 2 transitions, a disposition) matches repository behavior with zero leakage into the snapshot. Decision: **M043 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS.** Two non-blocking observations raised: M043-REVIEW-0001 (the finalization commit's own message cites a ZIP hash superseded by the final regenerated package; disclosed, not corrected via history rewrite) and M043-REVIEW-0002 (the implementation document states 253 formatted files; the independently and repeatedly reproduced figure is 252).

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31). Owner Freeze record: `MILESTONE_043_REVIEW_RETRIEVAL_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 47.

## 47. MILESTONE-043 Owner Freeze

**Owner Freeze record:** `MILESTONE_043_REVIEW_RETRIEVAL_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-043 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the 19-phase independent hostile macro review recorded in Section 46.

**Delivered capability, frozen:** retrieval of an existing `Review` by full frozen identity, via `GetReviewQuery`/`GetReviewHandler` (`src/empirical_platform/usecases/get_review.py`) — the fourth proof of the `get()`-retrieval pattern, closing the last query-side "zero verb-category proof" gap in the domain model. No `Review` lifecycle-transition work is authorized by this freeze.

**Frozen snapshot-boundary model:** `ReviewSnapshot` exposes exactly `identity`/`target_evidence_package_id`/`reviewer_reference`/`state`; independently confirmed via two separately authored adversarial scripts (unit-level and direct-SQL) that findings/transition history/disposition/rationale/cancellation reason/version/persisted version never leak, even from a genuinely populated `Review` (freeze record Sections 19-25, 35).

**Actual delivered package hash:** `cb81bff43cf47ec66ae352d9df765f53d74fcc2f7ca5e21550b1214ee8833177` (freeze record Section 41) — the finalization commit's own message cites a superseded intermediate hash (Section 42); this freeze record is the authoritative reference going forward.

**Freeze declaration:** `M043 MACRO MILESTONE APPROVED_AND_FROZEN`. `M043 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 48.

## 48. MILESTONE-044 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_044_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_LIFECYCLE_TRANSITION_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh, complete architecture inventory:** `Review` now has `create` (M042) and `get` (M043); it has zero command-side proof of `ReviewRepository.save()`/`OptimisticConcurrencyConflict` propagation. `grep` across all 14 `usecases` modules confirmed zero `.save(` call sites and zero `OptimisticConcurrencyConflict` references referencing `Review`. `ReviewRepository.save()`/`PostgresReviewRepository.save()` were both already frozen (M020/M023) with zero infrastructure gap.

**Selected scope:** one concrete command transitioning an existing, `ASSIGNED` `Review` to `IN_PROGRESS`, via `Review.start()` — the fourth proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern (after M032 Campaign, M035 Run, M038 EvidencePackage). `add_finding()`/`complete()` remain genuinely blocked behind `start()`'s own prior non-existence; `cancel()` and `EvidencePackage.invalidate()` were both evaluated and rejected as lower-leverage repeats of an already-proven pattern. Full candidate comparison: scope document Section 8.

**Conflict feasibility — genuinely determined, not assumed:** independently inspected `Review.aggregate` for any state-preserving mutation reachable while `ASSIGNED`, finding none exists — mirroring the identical reasoning M038's design independently discovered for `EvidencePackage.start_collection()`. A true `OptimisticConcurrencyConflict` reproduction via genuine, caller-driven, real-PostgreSQL evidence is therefore **not achievable** for `start()` specifically; two racing callers instead produce a domain-level `ValueError`, independently reproduced against real PostgreSQL. `OptimisticConcurrencyConflict` propagation itself is proven at the unit level via a fake repository, mirroring M038's identical, already-accepted resolution.

**Design:** a six-field command, field-for-field identical to `StartEvidencePackageCollectionCommand` (M038).

**Architecture impact:** none. `usecases` already had `review` in `ALLOWED["usecases"]` since M042. `tools/check_architecture.py` unchanged; `python tools/check_architecture.py .` exit 0.

**Tests:** 28 new (3 contract, 21 unit, 4 PostgreSQL integration — including the golden path and the two-racing-callers domain-`ValueError` race, all executed live against a fresh disposable container). Full non-integration suite: 790 passed (up from 766), 178 deselected, coverage 84.39%, zero regression. Full integration regression: 172 passed (up from 168). Full suite with PostgreSQL: 962 passed, 93.15% coverage.

**Hostile self-audit:** targeted prohibited-pattern grep on `start_review.py` found zero genuine matches; the `usecases/__init__.py` diff is purely additive; a full scope-creep sweep across the diff found zero genuine matches for `add_finding`/`complete`/`cancel`/`invalidate`/`M045`/composition-related tokens (the only match is a negative-assertion test name proving absence).

**Independent hostile macro review:** a 26-phase independent review, treating every source file, test, governance document, commit message, and packaged claim as potentially false, independently re-derived repository truth, M043 freeze ordering, a fresh architecture inventory at the exact M044 baseline commit tree, the honest non-overstated `cancel()` rejection reasoning, zero scope-creep across the full delta, exact command/handler/identity/expected-version verification via non-tautological adversarial scripts, and — most critically — a freshly authored direct-SQL adversarial script against a separately provisioned container that independently reproduced the full racing-callers sequence, confirming via raw SQL that the second caller genuinely receives a plain domain `ValueError` (never `OptimisticConcurrencyConflict`), with the final persisted state exactly the first writer's result. Decision: **M044 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — the review's own final report recorded zero surviving findings of any severity.

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31). Owner Freeze record: `MILESTONE_044_REVIEW_START_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 49.

## 49. MILESTONE-044 Owner Freeze

**Owner Freeze record:** `MILESTONE_044_REVIEW_START_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-044 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the 26-phase independent hostile macro review recorded in Section 48.

**Delivered capability, frozen:** transition of an existing, `ASSIGNED` `Review` to `IN_PROGRESS`, via `StartReviewCommand`/`StartReviewHandler` (`src/empirical_platform/usecases/start_review.py`) — the fourth proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern, closing the last command-side proof gap for `Review`.

**Frozen real-concurrency boundary:** `Review` has no state-preserving mutation reachable while `ASSIGNED`; genuine PostgreSQL-level `OptimisticConcurrencyConflict` is not achievable for `start()` specifically. Racing callers instead genuinely produce a domain-level `ValueError`, independently confirmed via a freshly authored direct-SQL adversarial script (freeze record Sections 35-37) — mirroring M038's identical, already-accepted boundary.

**Freeze declaration:** `M044 MACRO MILESTONE APPROVED_AND_FROZEN`. `M044 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 50.

## 50. MILESTONE-045 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_045_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_FINDING_RECORDING_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh, complete architecture inventory:** `Review` now has `create`, `get`, and `start` (M042/M043/M044); it has zero proof of `add_finding()` — the sole remaining Review capability whose prerequisite (`IN_PROGRESS` reachability) M044 specifically resolved. `complete()` remains blocked (requires non-empty `findings`); `cancel()` was reachable but offers no comparable architectural novelty.

**Selected scope:** one concrete command appending a new finding to an existing, `IN_PROGRESS` `Review`, via `Review.add_finding()` — the third proof of the owned-collection-append pattern (after M039 `add_criterion_result`, M040 `add_artifact_reference`), and the first for `Review`. Independently discovered architectural difference from M039/M040: `Review.add_finding()`'s `sequence` is always internally generated, never caller-supplied, so no duplicate-detection scenario is domain-reachable at all — documented honestly, not silently omitted.

**Conflict feasibility — empirically confirmed, not assumed:** unlike M044's `start()`, `add_finding()` is state-preserving (does not call `_transition()`, does not change `state`). A standalone probe and the integration test suite both independently confirmed, against real PostgreSQL, that a second, independently-loaded `add_finding()` call (the only state-preserving Review mutation available, used as its own interfering write) genuinely produces an unqualified `OptimisticConcurrencyConflict` — no domain-`ValueError` obstacle, no disclosed real-PostgreSQL boundary of the kind M038/M044 required. This is the third milestone (after M039, M040) to achieve genuine, unqualified conflict evidence.

**Design:** a five-field command, mirroring `add_finding()`'s own actual signature (not blindly copying `RecordEvidencePackageCriterionResultCommand`'s shape, which carries a `recorded_at` field `ReviewFinding` has no equivalent of).

**Architecture impact:** none. `usecases` already had `review` in `ALLOWED["usecases"]` since M042. `tools/check_architecture.py` unchanged; `python tools/check_architecture.py .` exit 0.

**Tests:** 30 new (3 contract, 22 unit, 5 PostgreSQL integration — including the genuine deterministic conflict reproduction, all executed live against a fresh disposable container). Full non-integration suite: 815 passed (up from 790), 183 deselected, coverage 84.49%, zero regression. Full integration regression: 177 passed (up from 172). Full suite with PostgreSQL: 992 passed, 93.38% coverage.

**Hostile self-audit:** targeted prohibited-pattern grep on `add_review_finding.py` found zero genuine matches; the `usecases/__init__.py` diff is purely additive; a full scope-creep sweep across the diff found zero genuine matches for `.complete(`/`.cancel(`/`invalidate`/`M046`/composition-related tokens (the only match is a negative-assertion test name proving absence).

**Independent hostile macro review:** a 28-phase independent review, treating every source file, test, governance document, commit message, and packaged claim as potentially false, independently re-derived repository truth, M044 freeze ordering, a fresh architecture inventory at the exact M045 baseline commit tree, exact command/handler/identity/expected-version/finding-mapping verification via a non-tautological adversarial script (2 newly adversarially chosen exception types), independent confirmation that no duplicate-`sequence` scenario is domain-reachable, and — most critically — a freshly authored direct-SQL adversarial script against a separately provisioned container that independently reproduced the full 16-step real-conflict sequence, confirming via raw SQL a genuine, unqualified `OptimisticConcurrencyConflict` with correct metadata, writer A's finding authoritative, writer B's finding never persisted. Decision: **M045 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — the review's own final report recorded zero surviving findings of any severity.

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31). Owner Freeze record: `MILESTONE_045_REVIEW_FINDING_RECORDING_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 51.

## 51. MILESTONE-045 Owner Freeze

**Owner Freeze record:** `MILESTONE_045_REVIEW_FINDING_RECORDING_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-045 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the 28-phase independent hostile macro review recorded in Section 50.

**Delivered capability, frozen:** appending one new finding to an existing, `IN_PROGRESS` `Review`, via `AddReviewFindingCommand`/`AddReviewFindingHandler` (`src/empirical_platform/usecases/add_review_finding.py`) — the third proof of the owned-collection-append pattern (after M039, M040), and the first for `Review`.

**Frozen real-conflict model:** a genuine, unqualified `OptimisticConcurrencyConflict` reproduction against real PostgreSQL, independently re-confirmed via a freshly authored direct-SQL adversarial script bypassing the ORM/test-framework layers, using a second `add_finding()` call (the only state-preserving Review mutation) as the interfering write (freeze record Section 22). No direct SQL fabrication, no patched aggregate internals, no invalid row, no second production command.

**Freeze declaration:** `M045 MACRO MILESTONE APPROVED_AND_FROZEN`. `M045 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 52.

## 52. MILESTONE-046 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_046_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_COMPLETION_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh, complete architecture inventory:** `Review` now has `create`, `get`, `start`, and `add_finding` (M042/M043/M044/M045); it has zero proof of `complete()` — the sole remaining Review capability whose full prerequisite chain (`IN_PROGRESS` reachability **and** non-empty `findings`) is newly, simultaneously satisfied. `cancel()` remains reachable but offers no comparable architectural novelty.

**Selected scope:** one concrete command completing an existing, `IN_PROGRESS` `Review` with non-empty `findings`, via `Review.complete()` — the fifth proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern (after M032, M035, M038, M044), and the second multi-precondition transition in this project's lineage (after M041 `seal()`).

**Conflict feasibility — empirically confirmed, not assumed:** unlike M044's `start()`, `Review` now has a second, distinct, state-preserving mutation (`add_finding()`, M045) available as a genuinely different interfering write. A standalone probe and the integration test suite both independently confirmed, against real PostgreSQL, that an interfering `add_finding()` call genuinely produces an unqualified `OptimisticConcurrencyConflict` against a racing `complete()` command — no domain-`ValueError` obstacle, no disclosed real-PostgreSQL boundary. This is the fourth milestone (after M039, M040, M045) to achieve genuine, unqualified conflict evidence.

**Design:** a seven-field command, mirroring `SealEvidencePackageCommand`'s shape (the only other multi-precondition transition) adapted for `complete()`'s own `disposition`/`final_disposition_rationale` fields in place of a generic `reason`.

**Architecture impact:** none. `usecases` already had `review` in `ALLOWED["usecases"]` since M042. `tools/check_architecture.py` unchanged; `python tools/check_architecture.py .` exit 0.

**Tests:** 33 new (3 contract, 24 unit, 6 PostgreSQL integration — including the genuine deterministic conflict reproduction, all executed live against a fresh disposable container). Full non-integration suite: 842 passed (up from 815), 189 deselected, coverage 84.59%, zero regression. Full integration regression: 183 passed (up from 177). Full suite with PostgreSQL: 1025 passed, 93.43% coverage.

**Hostile self-audit:** targeted prohibited-pattern grep on `complete_review.py` found zero genuine matches; the `usecases/__init__.py` diff is purely additive (an initial alphabetical-ordering slip was caught and corrected by `ruff` before commit); a full scope-creep sweep across the diff found zero genuine matches for `.cancel(`/`invalidate`/`M047`/composition-related tokens (the only match is a negative-assertion test name proving absence).

**Independent hostile macro review:** a 19-phase (Phase 0-19) independent review, treating every source file, test, governance document, commit message, and packaged claim as potentially false, independently re-derived repository truth, M045 freeze ordering, a fresh architecture inventory at the exact M046 baseline commit tree, exact command/handler/identity/expected-version verification via a non-tautological adversarial script, direct re-confirmation that `complete()`'s own state/findings checks fire before `_transition()`'s internal check (making the latter structurally unreachable on this path), transparent propagation of six adversarial exception scenarios, a full independent read and count of all 33 tests, and — most critically — a freshly authored direct-SQL adversarial script against a separately provisioned container that independently reproduced the genuine conflict scenario using a distinct `add_finding()` interferer, confirming via raw SQL a genuine, unqualified `OptimisticConcurrencyConflict` (exact type, not `ValueError`) with the interferer's write authoritative and the stale completion never persisted. Decision: **M046 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — one non-blocking documentation observation (`mypy src` vs. canonical bare `mypy` file-count difference, a pre-existing convention, not an M046 defect); zero CRITICAL/MAJOR/blocking MINOR findings.

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31). Owner Freeze record: `MILESTONE_046_REVIEW_COMPLETION_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 53.

## 53. MILESTONE-046 Owner Freeze

**Owner Freeze record:** `MILESTONE_046_REVIEW_COMPLETION_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-046 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the 19-phase independent hostile macro review recorded in Section 52.

**Delivered capability, frozen:** completing an existing, `IN_PROGRESS` `Review` with non-empty `findings`, via `CompleteReviewCommand`/`CompleteReviewHandler` (`src/empirical_platform/usecases/complete_review.py`) — the fifth proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern, and the second multi-precondition transition in this project's lineage (after M041 `seal()`).

**Frozen real-conflict model:** a genuine, unqualified `OptimisticConcurrencyConflict` reproduction against real PostgreSQL, independently re-confirmed via a freshly authored direct-SQL adversarial script bypassing the ORM/test-framework layers, using a distinct `add_finding()` call (a genuinely different, state-preserving Review mutation) as the interfering write (freeze record Sections 40-41). No direct SQL fabrication, no patched aggregate internals, no invalid row, no second production command.

**Freeze declaration:** `M046 MACRO MILESTONE APPROVED_AND_FROZEN`. `M046 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 54.

## 54. MILESTONE-047 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_047_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_CANCELLATION_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh, complete architecture inventory:** all four aggregates now have at least one proven `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` transition (Campaign M032, Run M035, EvidencePackage M038-M041, Review M044-M046) — that generalization axis is closed. A full domain-method inventory found Campaign and Run each carry the largest remaining absolute gap (7 of 8 domain methods unproven each), against EvidencePackage's and Review's single remaining gap each (`invalidate()`, `cancel()`). A second, cross-cutting gap was independently identified: no negative/terminal (cancellation, invalidation, failure) transition has ever been proven at the application layer, for any aggregate. A direct comparison of all five candidate methods (`EvidencePackage.invalidate()`, `Run.cancel()`, `Review.cancel()`, `Run.fail()`, `Campaign.cancel()`) found `Campaign.cancel()` uniquely combines the widest multi-state `allowed_states` reachability (5 states, versus 1-3 for every other candidate) with state-dependent conditional validation (`reason` required from `AUTHORIZED`/`ACTIVE`/`SUSPENDED`, optional from `DRAFT`/`READY_FOR_AUTHORIZATION`) — a precondition shape never exercised by any transition proven at M030-M046.

**Selected scope:** one concrete command cancelling an existing Campaign from any of its five non-terminal, non-completed states, via `Campaign.cancel()` — the sixth proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern, the first proof of a negative/terminal transition at the application layer for any aggregate, and the first proof of state-dependent conditional domain validation.

**Conflict feasibility — empirically confirmed, not assumed:** `Campaign.revise_scope_statement()` (M032's own frozen interfering write, `DRAFT`-only, state-preserving) was independently re-verified to genuinely serve as the interfering write against `cancel()` when cancelling from `DRAFT` — the identical M032 mechanism, re-applied to this new target transition and re-confirmed empirically (not assumed by analogy), against real PostgreSQL.

**Design:** a six-field command mirroring `Campaign.cancel()`'s own actual signature (`actor`, `occurred_at`, `reason=None`, `correlation_id=None`), plus the two universal `identity`/`expected_persisted_version` fields.

**Architecture impact:** none. `usecases` already had `campaign` in `ALLOWED["usecases"]` since M030. `tools/check_architecture.py` unchanged; `python tools/check_architecture.py .` exit 0.

**Tests:** 33 new (3 contract, 23 unit, 7 PostgreSQL integration — including the genuine deterministic conflict reproduction and both branches of the conditional `reason` validation, all executed live against a fresh disposable container). Full non-integration suite: 868 passed (up from 842), 196 deselected, coverage 84.69%, zero regression. Full integration regression: 190 passed (up from 183). Full suite with PostgreSQL: 1058 passed, 93.54% coverage.

**Hostile self-audit:** targeted prohibited-pattern grep on `cancel_campaign.py` found zero genuine matches; the `usecases/__init__.py` diff is purely additive; a full scope-creep sweep across the diff found zero genuine matches for `.suspend(`/`.resume(`/`.activate(`/`.complete(`/`.record_authorization(`/`M048`/composition-related tokens inside the production source itself (test fixtures call these predecessor domain methods directly, as documented test setup only, never through a production command).

**Independent hostile macro review:** a 27-phase independent review, treating every source file, test, governance document, commit message, and packaged claim as potentially false, independently re-derived repository truth, M046 freeze ordering, a fresh architecture inventory re-deriving the `allowed_states`/conditional-validation shape of all 5 negative-terminal candidates directly from source (confirming `Campaign.cancel()`'s selection is `HIGHEST_LEVERAGE`), an exhaustive 17-scenario domain-level probe of every allowed/terminal state and reason combination, transparent propagation of 6 adversarial exception scenarios using exception types distinct from the implementation's own self-audit, an independent count of all 33 tests, and — most critically — a freshly authored direct-SQL adversarial script against a separately provisioned container that independently reproduced the genuine conflict scenario using `revise_scope_statement()` as the interferer, confirming via raw SQL a genuine, unqualified `OptimisticConcurrencyConflict` (exact type, not `ValueError`) with the interferer's write authoritative and the stale cancellation never persisted. Decision: **M047 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — the review's own final report recorded zero findings of any severity.

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31). Owner Freeze record: `MILESTONE_047_CAMPAIGN_CANCELLATION_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 55.

## 55. MILESTONE-047 Owner Freeze

**Owner Freeze record:** `MILESTONE_047_CAMPAIGN_CANCELLATION_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-047 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the 27-phase independent hostile macro review recorded in Section 54.

**Delivered capability, frozen:** cancelling an existing Campaign from any of its five non-terminal, non-completed states, via `CancelCampaignCommand`/`CancelCampaignHandler` (`src/empirical_platform/usecases/cancel_campaign.py`) — the sixth proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern, the first proof of a negative/terminal transition at the application layer for any aggregate, and the first proof of state-dependent conditional domain validation.

**Frozen real-conflict model:** a genuine, unqualified `OptimisticConcurrencyConflict` reproduction against real PostgreSQL, independently re-confirmed via a freshly authored direct-SQL adversarial script bypassing the ORM/test-framework layers, using `Campaign.revise_scope_statement()` (M032's own interfering write, re-applied to this new target transition) as the interfering write (freeze record Sections 39-40). No direct SQL fabrication, no patched aggregate internals, no invalid row, no second production command.

**Freeze declaration:** `M047 MACRO MILESTONE APPROVED_AND_FROZEN`. `M047 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 56.

## 56. MILESTONE-048 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_048_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_EXECUTION_FAILURE_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh, complete architecture inventory:** `get()`/`add()`/`save()` remain proven for every aggregate (closed since M046). M047 additionally proved a negative/terminal transition (`Campaign.cancel()`) for the first time in this project, but on exactly one aggregate. A full domain-method inventory found Run now carries the single largest remaining absolute gap (7 of 8 domain methods unproven). A direct comparison of the four remaining negative/terminal candidates (`Run.cancel()`, `Run.fail()`, `Review.cancel()`, `EvidencePackage.invalidate()`) against the now-frozen `Campaign.cancel()` precedent found `Run.fail()` uniquely combines the second-widest `allowed_states` (3 elements) with a semantically distinct scenario (mid-execution failure, not deliberate abandonment) — the only remaining candidate that generalizes the negative/terminal axis to a new real-world scenario rather than merely repeating `Campaign.cancel()`'s own abandonment semantics on a narrower scale.

**Selected scope:** one concrete command failing an existing Run from any of its three execution-stage states (`ACQUIRING`, `NORMALIZING`, `VALIDATING`), via `Run.fail()` — the seventh proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern, and the first generalization of the negative/terminal-transition axis (opened by M047) to a second aggregate.

**Conflict feasibility — empirically confirmed, not assumed:** `Run.append_manifest()` (M035's own frozen interfering write, state-preserving across `_MANIFEST_APPEND_STATES`, a superset including all three of `fail()`'s allowed states) was independently re-verified to genuinely serve as the interfering write against `fail()` when failing from `ACQUIRING` — the identical M035 mechanism, re-applied to a third target transition (after `authorize()` and M047's own `revise_scope_statement()` reuse for `cancel()`) and re-confirmed empirically, against real PostgreSQL.

**Design:** a six-field command mirroring `Run.fail()`'s own actual signature (`reason` unconditionally required, unlike `Campaign.cancel()`'s state-dependent optionality), plus the two universal `identity`/`expected_persisted_version` fields.

**Architecture impact:** none. `usecases` already had `run` in `ALLOWED["usecases"]` since M033. `tools/check_architecture.py` unchanged; `python tools/check_architecture.py .` exit 0.

**Tests:** 30 new (3 contract, 21 unit, 6 PostgreSQL integration — including the genuine deterministic conflict reproduction, all executed live against a fresh disposable container). Full integration regression: 196 passed (up from 190). Full suite with PostgreSQL: 1088 passed (up from 1058), 93.65% coverage, zero regression.

**Hostile self-audit:** targeted prohibited-pattern grep on `fail_run.py` found zero genuine matches; the `usecases/__init__.py` diff is purely additive; a full scope-creep sweep across the diff found zero genuine matches for `.start_acquisition(`/`.start_normalization(`/`.start_validation(`/`.complete_execution(`/`.cancel(`/`M049`/composition-related tokens inside the production source itself (test fixtures call `start_acquisition()` directly, as documented test setup only, never through a production command).

**Independent hostile macro review:** a 27-phase independent review, treating every source file, test, governance document, commit message, and packaged claim as potentially false, independently re-derived repository truth, M047 freeze ordering, a fresh architecture inventory re-deriving the `allowed_states` shapes of all 4 remaining negative-terminal candidates directly from source (confirming `Run.fail()`'s selection is `HIGHEST_LEVERAGE`), an exhaustive 8-state domain-level probe of every source state (3 allowed with manifest preservation, 5 disallowed) plus signature-level confirmation that `reason` has no default, transparent propagation of 6 adversarial exception scenarios using exception types distinct from the implementation's own self-audit, an independent count of all 30 tests, and — most critically — a freshly authored direct-SQL adversarial script against a separately provisioned container that independently reproduced the genuine conflict scenario using `append_manifest()` as the interferer, confirming via raw SQL a genuine, unqualified `OptimisticConcurrencyConflict` (exact type, not `ValueError`) with the interferer's manifest authoritative and the stale failure never persisted. Decision: **M048 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — the review's own final report recorded zero findings of any severity.

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31). Owner Freeze record: `MILESTONE_048_RUN_EXECUTION_FAILURE_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 57.

## 57. MILESTONE-048 Owner Freeze

**Owner Freeze record:** `MILESTONE_048_RUN_EXECUTION_FAILURE_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-048 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the 27-phase independent hostile macro review recorded in Section 56.

**Delivered capability, frozen:** failing an existing Run from any of its three execution-stage states (`ACQUIRING`, `NORMALIZING`, `VALIDATING`), via `FailRunCommand`/`FailRunHandler` (`src/empirical_platform/usecases/fail_run.py`) — the seventh proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern, and the first generalization of the negative/terminal-transition axis (opened by M047's `Campaign.cancel()`) to a second aggregate.

**Frozen real-conflict model:** a genuine, unqualified `OptimisticConcurrencyConflict` reproduction against real PostgreSQL, independently re-confirmed via a freshly authored direct-SQL adversarial script bypassing the ORM/test-framework layers, using `Run.append_manifest()` (M035's own interfering write, re-applied to this third target transition) as the interfering write (freeze record Sections 40-41). No direct SQL fabrication, no patched aggregate internals, no invalid row, no second production command.

**Freeze declaration:** `M048 MACRO MILESTONE APPROVED_AND_FROZEN`. `M048 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 58.

## 58. MILESTONE-049 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_049_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_CANCELLATION_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh, complete architecture inventory:** the negative/terminal-transition axis (opened by M047, generalized to Run by M048) remains unproven for EvidencePackage and Review. A full domain-method inventory found both are exactly one method from complete application-layer proof. A direct comparison of the two completion candidates (`EvidencePackage.invalidate()`, `Review.cancel()`) found `Review.cancel()` is the stronger choice: it proves Review's own first multi-state `allowed_states` transition (2 elements, versus `invalidate()`'s already-thrice-proven single-state `expected_state` mechanism for EvidencePackage), and has a directly reachable, already-precedented conflict interferer (`add_finding()`), whereas `EvidencePackage` has no genuine state-preserving mutation reachable from `SEALED`.

**Selected scope:** one concrete command cancelling an existing Review from either of its two non-terminal states (`ASSIGNED`, `IN_PROGRESS`), via `Review.cancel()` — the eighth proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern, the second generalization of the negative/terminal-transition axis to a third aggregate, and the completion of Review's application-layer proof (4 of 4 domain methods) — the first aggregate in the project to reach full coverage.

**Conflict feasibility — empirically confirmed, not assumed:** `Review.add_finding()` (M045's own frozen interfering write, already reused once by M046 for `complete()`) was independently re-verified to genuinely serve as the interfering write against `cancel()` when cancelling from `IN_PROGRESS` — the third reuse of this mechanism, re-confirmed empirically, against real PostgreSQL.

**Design:** a six-field command mirroring `Review.cancel()`'s own actual signature (`reason` unconditionally required, matching M048's `Run.fail()` shape rather than M047's conditional `Campaign.cancel()`), plus the two universal `identity`/`expected_persisted_version` fields.

**Architecture impact:** none. `usecases` already had `review` in `ALLOWED["usecases"]` since M042. `tools/check_architecture.py` unchanged; `python tools/check_architecture.py .` exit 0.

**Tests:** 32 new (3 contract, 22 unit, 7 PostgreSQL integration — including the genuine deterministic conflict reproduction, all executed live against a fresh disposable container). Full integration regression: 203 passed (up from 196). Full suite with PostgreSQL: 1120 passed (up from 1088), 93.69% coverage, zero regression.

**Hostile self-audit:** targeted prohibited-pattern grep on `cancel_review.py` found zero genuine matches; the `usecases/__init__.py` diff is purely additive; a full scope-creep sweep across the diff found zero genuine matches for `.start(`/`.add_finding(`/`.complete(`/`M050`/composition-related tokens inside the production source itself (test fixtures call the existing, frozen `StartReviewHandler` and `Review.add_finding()`/`complete()` directly, as documented test setup only, never through a new production command).

**Independent hostile macro review:** a 27-phase independent review, treating every source file, test, governance document, commit message, and packaged claim as potentially false, independently re-derived repository truth, M048 freeze ordering, a fresh architecture inventory independently confirming `EvidencePackage.invalidate()` has no genuine interfering write reachable from `SEALED` (validating the scope document's central selection claim), an exhaustive 4-state domain-level probe of every source state and reason combination plus findings-preservation verification, transparent propagation of 6 adversarial exception scenarios using exception types distinct from all prior audits, an independent count of all 32 tests, and — most critically — a freshly authored direct-SQL adversarial script against a separately provisioned container that independently reproduced the genuine conflict scenario using `add_finding()` as the interferer, confirming via raw SQL a genuine, unqualified `OptimisticConcurrencyConflict` (exact type, not `ValueError`) with the interferer's finding authoritative and the stale cancellation never persisted. Decision: **M049 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — the review's own final report recorded zero findings of any severity.

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation are frozen as one consolidated unit per the Macro Milestone Protocol (Section 31). Owner Freeze record: `MILESTONE_049_REVIEW_CANCELLATION_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 59.

## 59. MILESTONE-049 Owner Freeze

**Owner Freeze record:** `MILESTONE_049_REVIEW_CANCELLATION_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-049 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the 27-phase independent hostile macro review recorded in Section 58.

**Delivered capability, frozen:** cancelling an existing Review from either of its two non-terminal states (`ASSIGNED`, `IN_PROGRESS`), via `CancelReviewCommand`/`CancelReviewHandler` (`src/empirical_platform/usecases/cancel_review.py`) — the eighth proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern, the second generalization of the negative/terminal-transition axis to a third aggregate, and the completion of Review's application-layer proof. Review is now the **first aggregate in the project with full application-layer domain-method coverage** (4/4 transition/mutation methods proven).

**Frozen real-conflict model:** a genuine, unqualified `OptimisticConcurrencyConflict` reproduction against real PostgreSQL, independently re-confirmed via a freshly authored direct-SQL adversarial script bypassing the ORM/test-framework layers, using `Review.add_finding()` (M045's own interfering write, re-applied to this fourth target transition — its third reuse) as the interfering write (freeze record Sections 39-40). No direct SQL fabrication, no patched aggregate internals, no invalid row, no second production command.

**Freeze declaration:** `M049 MACRO MILESTONE APPROVED_AND_FROZEN`. `M049 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 60.

## 60. MILESTONE-050 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_050_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_RETRIEVAL_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh, complete architecture inventory — the first deliberate strategic pivot in the project's history.** Mandated leverage reassessment (scope Section 4) independently confirmed from live source: every remaining domain-completion candidate (`EvidencePackage.invalidate()`, `Run.cancel()`, any Campaign/Run forward transition) repeats an already-proven mechanism shape (single-state, unconditionally-validated `_transition()`, proven 9+ times); meanwhile zero production code anywhere has ever constructed a real chain from configuration to a command/query result — all 21 frozen handlers (M030-M049) have only ever been invoked from hand-wired test fixtures, and "composition root" has been named in the Deferred Work/Out-of-Scope section of 18 consecutive milestones (M032-M049). Answer to the mandated question: **yes, platform integration now has higher leverage than another isolated domain transition.**

**Selected scope:** a real, production `entrypoints.get_campaign` composition root proving genuine end-to-end wiring for the first time in production code — `resolve_foundation_config()` → `PostgresPersistenceService` → the frozen M025 `PostgresRepositoryRuntime` → the frozen M031 `GetCampaignHandler`/`GetCampaignQuery` → the frozen `QueryEntryPoint` — invocable as a real CLI command (`empirical-platform-get-campaign`). Zero new business capability; reuses 100% already-frozen capabilities. Deliberately the narrowest possible slice: one read-only query, no generic dispatcher, no service locator, no transport/HTTP layer.

**Composition feasibility — empirically confirmed, not assumed:** against a fresh disposable `postgres:17` container, `run_get_campaign()` independently confirmed golden-path retrieval of a real, freshly-created Campaign, genuine `AggregateNotFound` propagation for a missing Campaign, genuine `ValueError` propagation for a malformed identifier, and genuine environment-based resolution of the production default `config` path — all with zero exception translation at the composition-function level.

**Design:** `run_get_campaign()` owns the full composition and the sole unit of work; `main()` performs only CLI-argument-count validation and delegates, catching nothing, mirroring `health.py`'s own complete absence of exception handling.

**Architecture impact:** `ALLOWED["entrypoints"]` extended to permit `identifiers`/`usecases`; a new `FORBIDDEN_IMPORT_PREFIXES["entrypoints"]` entry forbids direct `sqlalchemy`/`psycopg`/`boto3` imports while deliberately permitting `shared.persistence` composition. `python tools/check_architecture.py .` exit 0.

**Tests (original mission):** 11 new (7 unit, 4 PostgreSQL integration, all executed live against a fresh disposable container). Full integration regression: 207 passed (up from 203). Full suite with PostgreSQL: 1131 passed (up from 1120), 93.70% coverage, zero regression.

**Hostile self-audit (original mission):** targeted prohibited-pattern grep on `get_campaign.py` found exactly one `try:` (the `try/finally` guaranteeing `service.close()`, zero `except` clauses anywhere); a full scope-creep sweep across the diff found zero genuine matches for dispatcher/registry/locator/mediator/transport/M051-related tokens.

**Independent hostile macro review (first pass):** found one MAJOR, Owner-Freeze-blocking finding, M050-Y-1 — `service.initialize()` was called before the `try:` block opened in `run_get_campaign()`, so `finally: service.close()` never ran when `initialize()` itself raised (empirically reproduced: `close()` call count of zero against a controlled failure). Decision: **M050 MACRO MILESTONE REQUIRES CORRECTION**.

**Correction applied:** `service.initialize()` moved one line, from immediately before the `try:` to the first statement inside it — the entire service lifetime is now owned by one `try`/`finally` boundary. No other production line changed; no new abstraction, framework, or exception policy introduced. Three new focused unit tests added (`test_run_get_campaign_closes_service_when_initialize_raises` — independently confirmed to fail pre-fix and pass post-fix — plus two companion regression guards for the already-correct success and post-initialize-failure paths). Full suite with PostgreSQL after correction: 1134 passed (up from 1131 by exactly the 3 new tests), 6 skipped, 93.70% coverage, zero regression. Full correction record: `MILESTONE_050_..._MACRO_IMPLEMENTATION.md` Section 12.

**Second independent hostile macro re-review:** covering both the original mission and the M050-Y-1 correction, independently re-derived repository truth and commit lineage; the correction delta (exactly 6 files, a minimal 2-line production change); a fresh, non-reused reproduction of the pre-fix defect via a temporarily-restored original source file; a more thorough post-fix probe additionally proving zero downstream composition work occurs after a failed `initialize()`; independent re-execution of the actual pytest defect test against both pre-fix and post-fix source (FAILED, then PASSED); close-failure semantics classified SOUND; an unbiased re-run of the strategic-pivot assessment (unchanged conclusion); a second, independently-chosen failure mode (credential rejection against a live listening server, not merely connection-refused); five fresh architecture negative probes (all correctly rejected); and full regression/toolchain/package-integrity re-verification on a third independently-provisioned container, zero drift. Decision: **M050 CORRECTED MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — one MINOR, explicitly non-blocking cosmetic finding (a section-numbering gap in the Macro Implementation document), zero CRITICAL or MAJOR findings.

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation (as corrected) frozen as one consolidated unit per the Macro Milestone Protocol (Section 31), on the authority of two independent hostile macro reviews recorded above. Owner Freeze record: `MILESTONE_050_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_RETRIEVAL_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 61.

## 61. MILESTONE-050 Owner Freeze

**Owner Freeze record:** `MILESTONE_050_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_RETRIEVAL_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-050 scope, design, and implementation (as corrected for finding M050-Y-1) as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of two independent hostile macro reviews recorded in Section 60 — the first of which returned "REQUIRES CORRECTION," and the second of which, after the M050-Y-1 fix, returned "APPROVED WITH NON-BLOCKING OBSERVATIONS."

**Delivered capability, frozen:** the project's first real, production, end-to-end application composition — `entrypoints.get_campaign` (`run_get_campaign()` + thin `main()` CLI wrapper, `src/empirical_platform/entrypoints/get_campaign.py`), composing real configuration resolution, a real PostgreSQL persistence service, the frozen M025 `PostgresRepositoryRuntime`, and the frozen M031 `GetCampaignHandler`/`GetCampaignQuery`/`QueryEntryPoint` into one real, invocable flow, registered as the `empirical-platform-get-campaign` console script.

**Frozen resource-lifecycle shape (corrected):** service construction, followed immediately by a `try`/`finally` block whose `try` opens with `.initialize()` as its first statement and whose `finally` unconditionally calls `.close()` — independently re-verified to guarantee exactly one construction, one `.initialize()`, one `.close()`, one `PostgresRepositoryRuntime` construction per invocation, and zero downstream composition work when `.initialize()` fails.

**Freeze declaration:** `M050 MACRO MILESTONE APPROVED_AND_FROZEN`. `M050 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 62.

## 62. MILESTONE-051 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_051_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_CANCELLATION_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh, complete architecture inventory — deepening, not repeating, the M050 pivot.** Independently re-derived from live source: Campaign has 6 unproven mutation methods, Run has 6, EvidencePackage has 1 (`invalidate`), Review is complete (4/4, since M049). Every remaining Campaign/Run transition independently confirmed to repeat an already-proven single-state `_transition()` shape. `EvidencePackage.invalidate()` independently re-confirmed to have zero genuine interfering write reachable from `SEALED` (`add_criterion_result`/`add_artifact_reference`/`seal` all require `COLLECTING` explicitly) — selecting it would be the first rigor regression in this project's negative-transition axis. `entrypoints/` independently confirmed to contain exactly one composition root (M050's `get_campaign`, read-only) — the `expected_persisted_version`/`OptimisticConcurrencyConflict` dimension of a write command flowing through a real entrypoint remains completely unproven. M050's own scope document (Section 6) explicitly named this as "a natural, well-motivated candidate for a future milestone, once the read-side pattern is independently reviewed and frozen" — now true.

**Selected scope:** a real, production `entrypoints.cancel_campaign` composition root — the first write command composed through a production entrypoint — `resolve_foundation_config()` → `PostgresPersistenceService` → the frozen M025 `PostgresRepositoryRuntime` → the frozen M047 `CancelCampaignHandler`/`CancelCampaignCommand` → the frozen `CommandEntryPoint` (M029), invocable as a real CLI command (`empirical-platform-cancel-campaign`). Pairs with M050's own `get_campaign` on the same aggregate. Zero new business capability; reuses 100% already-frozen capabilities.

**Composition feasibility — empirically confirmed, not assumed:** against a fresh disposable `postgres:17` container, `run_cancel_campaign()` independently confirmed golden-path cancellation, genuine `AggregateNotFound` propagation, genuine invalid-state `ValueError` propagation, and — the dimension M050 could not exercise — a genuine, exact-type `OptimisticConcurrencyConflict` propagating through the entrypoint when a real independently-loaded interferer (`revise_scope_statement()`, reusing M047's own frozen mechanism) advances the persisted version out from under a stale caller.

**Design:** `run_cancel_campaign()` owns the full composition and the sole unit of work; applies the M050-Y-1 resource-lifecycle correction from the first line written (`.initialize()` as the first statement inside `try:`), independently sanity-checked via a fail-before/pass-after reintroduction of the defect during implementation.

**Architecture impact:** none. `ALLOWED["entrypoints"]`/`FORBIDDEN_IMPORT_PREFIXES["entrypoints"]` (both established by M050) already permit everything this milestone needs. `python tools/check_architecture.py .` exit 0.

**Tests:** 16 new (11 unit, 5 PostgreSQL integration, all executed live against a fresh disposable container). Full integration suite: 212 passed (up from 207). Full suite with PostgreSQL: 1150 passed (up from 1134), 93.71% coverage, zero regression.

**Hostile self-audit:** targeted prohibited-pattern grep on `cancel_campaign.py` found exactly one `try:`, zero `except`; construction/lifecycle counts confirmed exactly 1 each; zero domain/usecase/repository files touched; a bonus adversarial probe confirmed an impossibly-high claimed version transparently propagates the distinct, pre-existing `InvalidAggregateForPersistence` exception rather than being reclassified.

**Independent hostile macro review:** a complete independent review, treating every source file, test, governance document, evidence artifact, reported count, commit, manifest, console script, and ZIP as potentially false, independently re-derived the full 8-file lineage, reconfirmed `EvidencePackage.invalidate()`'s evidentiary gap and M050's own genuine pre-authorization text, read `cancel_campaign.py` in full confirming pure composition with zero direct `.get()`/`.cancel()`/`.save()` calls, independently reproduced the resource-lifecycle regression (fresh probe plus a fail-before/pass-after defect reintroduction), five fresh architecture negative probes, a direct-SQL PostgreSQL success verification, a freshly-authored genuine-conflict probe with direct-SQL confirmation that the losing cancellation never persisted, an independently-authored impossibly-high-version probe, full regression/toolchain re-verification with zero drift, and independent package-integrity verification (ZIP SHA-256 matched exactly from disk). Decision: **M051 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS** — zero findings of any severity.

**Status:** `APPROVED_AND_FROZEN`. Scope, design, and implementation frozen as one consolidated unit per the Macro Milestone Protocol (Section 31), on the authority of the independent hostile macro review recorded above. Owner Freeze record: `MILESTONE_051_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_CANCELLATION_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 63.

## 63. MILESTONE-051 Owner Freeze

**Owner Freeze record:** `MILESTONE_051_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_CANCELLATION_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-051 scope, design, and implementation as one consolidated unit, per the Macro Milestone Protocol (Section 31), on the authority of the independent hostile macro review recorded in Section 62.

**Delivered capability, frozen:** the project's first write-side production composition entrypoint — `entrypoints.cancel_campaign` (`run_cancel_campaign()` + thin `main()` CLI wrapper, `src/empirical_platform/entrypoints/cancel_campaign.py`), composing real configuration resolution, a real PostgreSQL persistence service, the frozen M025 `PostgresRepositoryRuntime`, and the frozen M047 `CancelCampaignHandler`/`CancelCampaignCommand`/`CommandEntryPoint` into one real, invocable flow, registered as the `empirical-platform-cancel-campaign` console script. Pairs with M050's own `get_campaign` on the same aggregate — the platform-integration pivot is now proven on both halves of the CQRS boundary.

**Frozen version-trust boundary:** the entrypoint never calls `.get()` itself and never re-derives the current persisted version — the caller's own `expected_persisted_version` flows unchanged into `CancelCampaignCommand`, independently re-verified via source read and via two distinct live-PostgreSQL probes (a genuine stale-version `OptimisticConcurrencyConflict` and an impossibly-high-version `InvalidAggregateForPersistence`, both transparently propagated, neither reclassified).

**Frozen resource-lifecycle shape:** identical in kind to M050's own corrected shape — service construction, followed immediately by a `try`/`finally` block whose `try` opens with `.initialize()` as its first statement and whose `finally` unconditionally calls `.close()` — independently re-verified to guarantee exactly one construction, one `.initialize()`, one `.close()`, one `PostgresRepositoryRuntime` construction per invocation, and zero downstream composition work when `.initialize()` fails.

**Freeze declaration:** `M051 MACRO MILESTONE APPROVED_AND_FROZEN`. `M051 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 64.

## 64. MILESTONE-052 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (all candidate, produced in one consolidated mission):** `MILESTONE_052_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_CREATION_MACRO_SCOPE.md`, `..._MACRO_DESIGN.md`, `..._MACRO_IMPLEMENTATION.md`.

**Fresh, complete architecture inventory.** Independently re-derived: `entrypoints/` composed exactly 2 of 20 already-frozen usecases (`get_campaign`, `cancel_campaign`); 18 remain unreachable by any real caller, including every aggregate's own creation command. No production entrypoint had ever exercised the repository's `.add()` code path or constructed `UuidRuntimeIdentifierGenerator`. Answer to the product-execution-gap question ("what still prevents a real external caller from executing a meaningful workflow?"): **nothing can be created** — the literal first step of every workflow has no production entry point.

**Selected scope:** `entrypoints.create_campaign`, composing the frozen M030 `CreateCampaignHandler`/`CreateCampaignCommand` through a real CLI command (`empirical-platform-create-campaign`), completing a full create→retrieve→cancel real-world-usable trio for Campaign. Zero new business capability.

**FoundationRuntime investigated and rejected:** a hostile self-review caught and corrected an initial false claim that `UuidRuntimeIdentifierGenerator` was entirely unconstructed in production code — it is constructed inside `bootstrap.py`'s `FoundationRuntime`, which independent investigation found (a) is never invoked by any production entrypoint, and (b) carried its own uncorrected M050-Y-1-class resource-lifecycle defect. Decision: continue the established ad-hoc composition pattern rather than adopt `FoundationRuntime`. The flagged defect was separately corrected out of band (commit `1bff790`) while this mission was in progress; M052's own baseline was updated to sit on top of that correction (see governance Section 7 for the full explanation) — this mission's own diff does not touch `bootstrap.py`.

**Anti-abstraction gate applied:** cross-entrypoint duplication between `get_campaign.py`/`cancel_campaign.py` was directly measured (~10 lines of trivial boilerplate) and found insufficient to justify any shared composition helper, base class, or facade — explicit composition continues unabstracted for the third entrypoint.

**Composition feasibility — empirically confirmed, not assumed:** against a fresh disposable `postgres:17` container, `run_create_campaign()` independently confirmed a golden-path creation using the **real, non-deterministic** `UuidRuntimeIdentifierGenerator` (verified via direct-SQL read-back), a deterministic-override identity, a genuine `AggregateAlreadyExists`, a genuine `ValueError`, and genuine environment-based default-config resolution.

**Architecture impact:** none. `python tools/check_architecture.py .` exit 0, zero diff to `tools/check_architecture.py`.

**Tests:** 16 new (11 unit, 5 PostgreSQL integration, all executed live against a fresh disposable container). Full suite with PostgreSQL: 1168 passed (up from the true concurrent-corrected baseline of 1152), 93.73% coverage, zero regression.

**Hostile self-audit:** targeted prohibited-pattern grep on `create_campaign.py` found exactly one `try:`, zero `except`; construction/lifecycle counts confirmed exactly 1 each; zero domain/usecase/repository files touched; the M050-Y-1 regression guard was independently sanity-checked via a fail-before/pass-after defect reintroduction during implementation.

**Independent hostile macro review:** re-derived repository truth and the M052 delta from live Git history; confirmed the concurrent M026 bootstrap correction is legitimate, narrow, and untouched by M052's own diff. Performed one materially stronger check beyond all prior evidence: invoked the actual CLI entrypoint as a real subprocess against a fresh disposable PostgreSQL container — golden-path creation genuinely persisted (verified via raw `psql`), missing-argument and duplicate-governance-id error paths both propagated correctly with exit code 1 through the full external-process stack. Zero CRITICAL, MAJOR, or MINOR findings; no correction required.

**Status:** `APPROVED_AND_FROZEN`. Owner Freeze record: `MILESTONE_052_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_CREATION_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 65.

## 65. MILESTONE-052 Owner Freeze

**Owner Freeze record:** `MILESTONE_052_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_CREATION_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-052 scope, design, and implementation as one consolidated unit, on the authority of the independent hostile macro review recorded in Section 64.

**Delivered capability, frozen:** `entrypoints.create_campaign` — the third platform-integration entrypoint, completing a full create→retrieve→cancel real-world-usable trio for Campaign.

**Freeze declaration:** `M052 MACRO MILESTONE APPROVED_AND_FROZEN`. `M052 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 66.

## 66. MILESTONE-053 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents (reduced-ceremony process now in effect):** one consolidated `MILESTONE_053_EVIDENCE_SUBMISSION_WORKFLOW_SCOPE_AND_DESIGN.md` (scope + design in one document) and one consolidated `..._MACRO_MILESTONE_FREEZE.md` (implementation evidence + both review passes + owner approval in one document) — two governance documents total, down from M052's four, per this mission's explicit ceremony-reduction directive.

**Fresh, product-oriented architecture inventory.** Independently re-derived: exactly 3 of 20 already-frozen usecases were reachable by any real caller as of the M052 freeze (`create_campaign`, `get_campaign`, `cancel_campaign`); the entire application layers of Run, EvidencePackage, and Review remained reachable only from test fixtures. A Campaign could be created and cancelled, but nothing could be *done* with it. BEFORE/AFTER: before M053 the platform cannot record or seal any evidence for any Run; after M053 an external caller can create a Run, create an EvidencePackage, record criterion results and artifact references, seal it, and retrieve the final sealed state, entirely through real CLI commands against real PostgreSQL, with an automated end-to-end test proving the whole chain.

**Selected scope:** eight new production entrypoints composing eight already-frozen usecases (M033-M041) — `create_run`, `get_run`, `create_evidence_package`, `get_evidence_package`, `start_evidence_package_collection`, `record_evidence_package_criterion_result`, `record_evidence_package_artifact_reference`, `seal_evidence_package`. Zero new business/domain capability; every command, handler, aggregate, and repository touched is already frozen and unmodified.

**Anti-abstraction gate reassessed and overturned, narrowly.** M050-M052 each measured 2-3 files of trivial duplication and found no abstraction justified. Eight new entrypoints repeating the identical resource-lifecycle skeleton — the exact defect class already found twice (M050-Y-1, the M026 bootstrap correction) — changed that calculus. Decision: extract exactly one narrow helper, `entrypoints._composition.postgres_repository_runtime()`, owning only the resource-lifecycle boundary, with zero handler/command/dispatch awareness. M050-M052's own entrypoints are deliberately not retrofitted.

**Tests:** 47 new focused unit tests (composition-helper resource lifecycle including a fail-before/pass-after defect-reintroduction proof, Run-entrypoint CLI tests, EvidencePackage-entrypoint CLI tests) plus one comprehensive PostgreSQL end-to-end acceptance test (4 tests) proving the full chain against a real, disposable Docker container, including a genuine optimistic-concurrency conflict from two sequential criterion-result recordings and the two new failure modes this slice introduces (seal without evidence; record before collection started). Full regression: 998 non-integration tests passed (84.65% coverage), 221 PostgreSQL integration tests passed (6 pre-existing unrelated skips), zero regressions.

**Hostile self-review (Part C):** reviewed all 9 new files against resource leaks, transaction boundaries, partial persistence, lifecycle validity, identity/version correctness, error swallowing, hidden coupling, fake/unreachable integration, test-only wiring, and accidental scope expansion. Zero findings requiring correction.

**Independent second review (Part D):** re-derived repository truth fresh; performed a second, independent verification technique beyond the automated suite — real subprocess invocation of every CLI entrypoint (`python -m empirical_platform.entrypoints.<name>`) against a second fresh disposable PostgreSQL container, including a genuine `OptimisticConcurrencyConflict` and a genuine double-seal `ValueError`, both with exit code 1 — then independently verified final state via raw `psql`, bypassing all application code. Zero CRITICAL, MAJOR, or MINOR findings; no correction required.

**Status:** `APPROVED_AND_FROZEN`. Owner Freeze record: `MILESTONE_053_EVIDENCE_SUBMISSION_WORKFLOW_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 67.

## 67. MILESTONE-053 Owner Freeze

**Owner Freeze record:** `MILESTONE_053_EVIDENCE_SUBMISSION_WORKFLOW_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-053 scope, design, implementation, hostile self-review, and independent second review as one consolidated unit.

**Delivered capability, frozen:** the Evidence Submission Workflow — Run creation/retrieval and the full EvidencePackage collection lifecycle (create, start collection, record criterion results, record artifact references, seal, retrieve), composed into eight real CLI entrypoints against real PostgreSQL.

**Freeze declaration:** `M053 MACRO MILESTONE APPROVED_AND_FROZEN`. `M053 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 68.

## 68. MILESTONE-054 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents:** `MILESTONE_054_REVIEW_WORKFLOW_PRODUCTION_COMPOSITION_SCOPE_AND_DESIGN.md` (scope + design) and `..._MACRO_MILESTONE_FREEZE.md` (implementation evidence + both review passes + owner approval) — two governance documents, continuing the reduced-ceremony convention established in M053.

**Fresh, product-oriented architecture inventory.** Independently re-derived: Review is the only aggregate with 100% frozen usecase coverage (`create`, `get`, `start`, `add_finding`, `complete`, `cancel` — all 6, M042/M043/M044/M045/M046/M049) and zero production reachability. A caller could produce sealed evidence via M053 but had nowhere to take it next.

**Selected scope, extended per this mission's own instruction to prefer the larger safe continuation:** all six Review entrypoints, proven not merely in isolation but as a genuine cross-milestone continuation — a real EvidencePackage driven to SEALED through the frozen M052/M053 entrypoints, then directly into a full Review lifecycle. `CreateReviewCommand` targets an `EvidencePackageId` with no state precondition (DB-FK-enforced only, identical shape to M053's own `create_run`/`create_evidence_package`), which is what made this larger continuation safe.

**Reuse, no new abstraction.** The M053 `_composition.py` helper is reused unchanged for all six entrypoints; M050-M053's own entrypoints remain untouched.

**One genuine, minimal correction made inside this milestone (not a separate milestone):** `usecases/complete_review.py`'s `ReviewDisposition` import needed to become an explicit re-export (`import X as X`) for `entrypoints.complete_review` to construct it under mypy strict mode while staying within the architecture boundary (`entrypoints` cannot import `review` directly). One-line, zero-behavior-change fix; zero regression in the existing M046 suites.

**Tests:** 28 new focused unit tests plus one comprehensive PostgreSQL end-to-end acceptance test (5 tests) proving the full continuation from a genuinely sealed EvidencePackage through a completed Review, including a genuine optimistic-concurrency conflict and the two new failure modes this slice introduces (complete without any finding; add finding before start). Full regression: 1026 non-integration tests passed (84.28% coverage), 226 PostgreSQL integration tests passed (6 pre-existing unrelated skips), zero regressions.

**Hostile self-review:** confirmed zero `try:`/`except` and zero direct repository calls in any of the 6 new entrypoints; traced every version transition against independently-verified direct-SQL state. Zero findings beyond the explicit-re-export correction above.

**Independent second review:** real subprocess invocation of the entire cross-milestone chain (seed through M052/M053 entrypoints to a genuinely SEALED EvidencePackage, then all 6 new M054 entrypoints, including a genuine complete-without-findings failure and a genuine stale-version conflict) against a second fresh disposable PostgreSQL container, independently cross-checked via raw `psql`. Zero CRITICAL, MAJOR, or MINOR findings.

**Status:** `APPROVED_AND_FROZEN`. Owner Freeze record: `MILESTONE_054_REVIEW_WORKFLOW_PRODUCTION_COMPOSITION_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 69.

## 69. MILESTONE-054 Owner Freeze

**Owner Freeze record:** `MILESTONE_054_REVIEW_WORKFLOW_PRODUCTION_COMPOSITION_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-054 scope, design, implementation, hostile self-review, and independent second review as one consolidated unit.

**Delivered capability, frozen:** the Review Workflow Production Composition — create, start, record findings, complete, cancel, and retrieve a Review, composed into six real CLI entrypoints against real PostgreSQL, continuing directly from a genuinely sealed EvidencePackage.

**Freeze declaration:** `M054 MACRO MILESTONE APPROVED_AND_FROZEN`. `M054 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 70.

## 70. MILESTONE-055 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents:** `MILESTONE_055_RUN_EXECUTION_LIFECYCLE_SCOPE_AND_DESIGN.md` (scope + design) and `..._MACRO_MILESTONE_FREEZE.md` (implementation evidence + both review passes + owner approval) — two governance documents, continuing the reduced-ceremony convention.

**Fresh Run architecture inventory.** Independently re-derived from source: all seven Run lifecycle transition methods (`authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`) plus `append_manifest()` already existed on the frozen `Run` aggregate, requiring zero new domain design. Only `create_run`, `get_run`, `authorize_run`, `fail_run` usecases existed; `authorize_run`/`fail_run` had zero production entrypoints. No usecases existed at all for `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, or `append_manifest`.

**Selected scope:** five new usecases (`start_run_acquisition`, `append_run_manifest`, `start_run_normalization`, `start_run_validation`, `complete_run_execution`) plus seven new entrypoints composing them and the two already-frozen M035/M048 usecases — the complete legal forward Run execution lifecycle, plus the negative `fail_run` path. `cancel_run` explicitly identified and excluded (different terminal path, no usecase, not requested).

**One genuine, minimal correction made inside this milestone:** `run/__init__.py` gained a two-line, zero-behavior-change re-export of `DatasetManifest` (which lives in the separate `datasets` package, unlike `EvidencePackage`/`Review`'s own owned value objects), required because `usecases` cannot import `datasets` directly and this is the first usecase ever needing Run's owned manifest type. Zero regression in 36 pre-existing Run-related contract/mapper/reconstruction tests.

**Tests:** 54 new focused tests (18 usecase, 36 entrypoint CLI) plus one comprehensive PostgreSQL end-to-end acceptance test (5 tests) proving the complete legal lifecycle against a real, disposable Docker container, including a genuine optimistic-concurrency conflict during manifest recording, the negative `fail_run` path with manifest-data preservation, and the two new failure modes this slice introduces (out-of-order transition; post-completion manifest append). Full regression: 1080 non-integration tests passed (84.29% coverage), 231 PostgreSQL integration tests passed (6 pre-existing unrelated skips), zero regressions.

**Hostile self-review:** attacked all 13 questions from the mission's own checklist — reachability, precondition bypass, state fabrication, caller-controlled version, partial-execution corruption, data preservation, transition-history correctness, negative-path correctness, resource cleanup, business-logic leakage, unnecessary predecessor changes, accidental scope expansion, and tautological tests. Zero findings beyond the explicit re-export correction above.

**Independent second review:** real subprocess invocation of the entire chain against a second fresh disposable PostgreSQL container, driving one Run to `EXECUTION_COMPLETED` (with a genuine `OptimisticConcurrencyConflict` and corrected retry, and a genuine post-completion `ValueError`) and one Run to `FAILED` from `ACQUIRING` with manifest data intact, independently cross-checked via raw `psql` against both Runs' final states, manifests, and complete transition histories. Zero CRITICAL, MAJOR, or MINOR findings.

**Status:** `APPROVED_AND_FROZEN`. Owner Freeze record: `MILESTONE_055_RUN_EXECUTION_LIFECYCLE_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 71.

## 71. MILESTONE-055 Owner Freeze

**Owner Freeze record:** `MILESTONE_055_RUN_EXECUTION_LIFECYCLE_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-055 scope, design, implementation, hostile self-review, and independent second review as one consolidated unit.

**Delivered capability, frozen:** the Run Execution Lifecycle End-to-End — authorize, start acquisition, record dataset manifests, start normalization, start validation, complete execution, and fail, composed into seven real CLI entrypoints against real PostgreSQL.

**Freeze declaration:** `M055 MACRO MILESTONE APPROVED_AND_FROZEN`. `M055 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** see Section 72.

## 72. MILESTONE-056 Macro Milestone Mission (APPROVED_AND_FROZEN)

**Governance documents:** `MILESTONE_056_CAMPAIGN_LIFECYCLE_SCOPE_AND_DESIGN.md` (scope + design) and `..._MACRO_MILESTONE_FREEZE.md` (implementation evidence + both review passes + owner approval + core engine closure assessment) — two governance documents, continuing the reduced-ceremony convention.

**Fresh Campaign architecture inventory.** Independently re-derived from source: all mutation methods (`revise_scope_statement`, `prepare_for_authorization`, `record_authorization`, `activate`, `suspend`, `resume`, `complete`, `cancel`) already existed on the frozen `Campaign` aggregate, requiring zero new domain design. Only `create_campaign`, `get_campaign`, `prepare_campaign_for_authorization`, `cancel_campaign` usecases existed; `prepare_campaign_for_authorization` had zero production entrypoint. No usecases existed for `revise_scope_statement`, `record_authorization`, `activate`, `suspend`, `resume`, or `complete`.

**Selected scope:** six new usecases plus seven new entrypoints composing them and the already-frozen M032 `prepare_campaign_for_authorization` usecase — the complete legal forward Campaign lifecycle including the suspend/resume side-path, plus scope-statement revision in DRAFT as a concrete Campaign-owned-data preservation proof. The already-frozen M047/M051 `cancel_campaign` was integrated as this milestone's negative path, not rebuilt.

**No predecessor source file required correction this time** (unlike M055's `run/__init__.py` situation) — `CampaignScopeStatement` already lives inside the `campaign` package, which `usecases` may already import directly per the architecture boundary.

**Tests:** 48 new focused tests (15 usecase, 33 entrypoint CLI) plus one comprehensive PostgreSQL end-to-end acceptance test (4 tests) proving the complete legal lifecycle with scope-statement preservation, plus one cross-aggregate acceptance test proving Campaign, Run, EvidencePackage, and Review can be driven sequentially by a real caller through their existing production entrypoints alone. Full regression: 1128 non-integration tests passed (84.35% coverage), 236 PostgreSQL integration tests passed (6 pre-existing unrelated skips), zero regressions.

**Concurrency decision:** no new OCC scenario added — Campaign OCC is already exhaustively proven by M047, and this milestone introduces no materially new concurrency boundary. Lifecycle acceptance was prioritized instead, per the mission's own instruction.

**Hostile self-review:** attacked all 14 questions from the mission's own checklist — reachability, precondition bypass, state fabrication, caller-controlled version, transition-history correctness, data preservation, failure transparency, resource cleanup, business-logic leakage, unnecessary predecessor changes, accidental scope expansion, tautological tests, and BEFORE/AFTER truth. Zero findings requiring correction.

**Independent second review:** real subprocess invocation of the entire chain against a second fresh disposable PostgreSQL container, driving one Campaign to `COMPLETED` (including a genuine post-DRAFT scope-revision `ValueError`, and `get_campaign` confirming data preservation across all six subsequent transitions) and one Campaign to `CANCELLED` from `ACTIVE`, independently cross-checked via raw `psql`. Zero CRITICAL, MAJOR, or MINOR findings.

**Core engine closure assessment:** Campaign, Run, EvidencePackage, and Review are now each independently composed into real production entrypoints AND proven sequentially composable by a real caller with no new orchestration layer (this milestone's own cross-aggregate acceptance test). **The core engine is now functionally closed.** Recommendation: future work should move toward trading-product integration rather than further aggregate-completeness milestones.

**Status:** `APPROVED_AND_FROZEN`. Owner Freeze record: `MILESTONE_056_CAMPAIGN_LIFECYCLE_MACRO_MILESTONE_FREEZE.md`.

**Next permitted action:** see Section 73.

## 73. MILESTONE-056 Owner Freeze

**Owner Freeze record:** `MILESTONE_056_CAMPAIGN_LIFECYCLE_MACRO_MILESTONE_FREEZE.md`. Freezes MILESTONE-056 scope, design, implementation, hostile self-review, independent second review, and core engine closure assessment as one consolidated unit.

**Delivered capability, frozen:** the Campaign Lifecycle End-to-End — revise scope, prepare for authorization, record authorization, activate, suspend, resume, and complete, composed into seven real CLI entrypoints against real PostgreSQL, plus proof that the full Campaign→Run→EvidencePackage→Review core engine is now sequentially usable by a real caller.

**Freeze declaration:** `M056 MACRO MILESTONE APPROVED_AND_FROZEN`. `M056 APPROVED_AND_FROZEN`.

**Status:** `APPROVED_AND_FROZEN`.

**Next permitted action:** MILESTONE-057 — recommendation: trading-product integration (see M056 final report Section Y). Not yet selected or started.
