# Architecture diagrams / Diagramas de la arquitectura

**Diseño de arquitectura:** Daniel Pineda González  
**Qué responde:** cómo fluye un turno, cómo se mueve la conversación y qué hace el sistema cuando algo sale mal.  
Los diagramas están en inglés para quien evalúe sin leer español; cada uno nombra el nodo o documento donde está el detalle.

The model understands; the code decides. Three drawings show it: one turn, the conversation states, and every exception.

## 0. The whole map: macro-process, processes, procedures

![Process map](presentacion/mapa_proceso_en.svg)

Escalation: when the policy says "not alone" (risk, high amount, doubt, no model) or a re-read does not match, the code builds the handoff package,
**tells the customer who takes the case and the expected wait**, and the router sends it to the right team. **The way back:** the agent sees the package
and does not ask again; they answer in the same chat, **return the case to the assistant with a note**, or transfer it with a note. An open claim follows
its investigation and the customer is told when it closes; when the customer comes back, the process starts again from the last re-read event.

| Level | What it is | Where it lives |
|---|---|---|
| Macro-process | Handle an unrecognized charge, end to end | this page · `PROCESOS.md` §0 |
| Processes P1–P9 | Each flow with its trigger and end | `docs/PROCESOS.md` (BPMN-style lanes; no BPM engine) |
| State machine N0–N14 | Conversation steps and edges | `docs/ARQUITECTURA.md` §6 · `servicio/orquestador/` |
| Policy (admissibility filter: four checks that must all pass) | Four checks run by code + country rules | `servicio/politica/motor.py` · `politica/comun.yaml`, `politica/{mx,co,ar}.yaml` |
| Procedures | Agent guides, protocols, knowledge articles | `config/guias_asesor.yaml` · `docs/CASOS.md` · `conocimiento/` |
| Evidence | Execution log, database re-read, evaluation | `evaluacion/` |

## 1. One turn, end to end

Purple boxes are the only places a language model is used. Everything else is code with a contract, or a person.

```mermaid
flowchart TB
    C([Customer message]) --> F["1 · Sensitive-data filter<br/>card numbers and PINs erased<br/>before anything is saved"]
    F --> I["2 · Interpreter (model)<br/>describes the message:<br/>language, commands, risk signals"]
    I --> V["3 · Validator<br/>closed catalog and strict schema"]
    V --> S["4 · State machine (code)<br/>decides the next step"]
    S --> D["5 · Real candidates<br/>SQL with row-level security<br/>the customer comes from the token"]
    D --> P["6 · Policy: 4 checks<br/>a pure function of verified facts"]
    P -->|human review| H(["Handoff to a person<br/>with the full package"])
    P -->|action needs consent| K{{"7 · Customer confirms<br/>this action, this session"}}
    K --> T["8 · Tool (code)<br/>idempotent write"]
    T --> R["9 · Re-read the real state<br/>nothing is claimed until it matches"]
    R --> W
    P -->|only information| W["10 · Writer (model)<br/>writes from verified facts only"]
    W --> X["11 · Verifier (code)<br/>figures, actions, language"]
    X --> O([Answer to the customer])
    classDef modelo fill:#9b6bd1,color:#fff,stroke:#4a1f73
    classDef codigo fill:#4a1f73,color:#fff,stroke:#4a1f73
    classDef persona fill:#127a4b,color:#fff,stroke:#0b5133
    class I,W modelo
    class F,V,S,D,P,T,R,X codigo
    class H persona
```

*Detail: `ARQUITECTURA.md` §3 and §6.*

## 2. The conversation state machine

Fifteen nodes. The state is saved in the database at every turn: there is no hidden memory.

```mermaid
stateDiagram-v2
    direction TB
    state "N0 No session" as N0
    state "N1 Authenticating" as N1
    state "N2 Listening" as N2
    state "N3 Finding the charge" as N3
    state "N4 Clarifying" as N4
    state "N5 Showing facts" as N5
    state "N6 Evaluating" as N6
    state "N7 Proposing" as N7
    state "N8 Executing" as N8
    state "N9 Verifying" as N9
    state "N10 Resolved" as N10
    state "N11 Handoff to a person" as N11
    state "N12 Closed, no claim" as N12
    state "N13 Out of scope" as N13
    state "N14 Abstaining" as N14

    [*] --> N0
    N0 --> N1: needs account data
    N1 --> N2: valid token
    N1 --> N11: 3 failed codes
    N0 --> N11: cannot identify
    N2 --> N3: reports a charge
    N2 --> N4: no data yet
    N2 --> N13: other banking request
    N2 --> N14: not banking, or manipulation
    N2 --> N11: asks for a person, or risk signal
    N3 --> N5: exactly 1 candidate
    N3 --> N4: 0 or many candidates
    N4 --> N3: new data or a choice
    N4 --> N11: no progress
    N5 --> N12: customer recognizes it
    N5 --> N11: recognizes it but was scammed
    N5 --> N6: does not recognize it
    N6 --> N7: policy allows automation
    N6 --> N11: human review
    N7 --> N8: explicit confirmation
    N7 --> N12: customer declines
    N7 --> N11: asks for a person
    N8 --> N9: tool answered
    N8 --> N11: error after bounded retries
    N9 --> N10: re-read matches
    N9 --> N11: mismatch or unknown
    N10 --> [*]
    N11 --> [*]
    N12 --> [*]
```

An expired or invalid token sends any node back to N1 (the confirmation is asked again after re-identifying).
A side question (hours, how a claim works) is answered and the conversation returns to the same node, untouched.

*Detail: `ARQUITECTURA.md` §6.1 and §6.2.*

## 3. When something goes wrong

Every exception ends in one of three safe outcomes: the system retries within a bound, it asks the customer, or a person takes the case. It never invents an answer and never claims an action it did not verify.

```mermaid
flowchart LR
    X{{"Something<br/>goes wrong"}}
    X --> a1["The model fails<br/>or is slow"] --> a2["Bounded retries,<br/>then the circuit opens"] --> a3["NO MODEL: routed by state,<br/>no canned phrases,<br/>nothing executed"] --> a4(["Handoff to a person<br/>with context and the real wait"])
    X --> b1["The model's output<br/>is malformed"] --> b2["Validator rejects it<br/>and asks once more"] --> b3(["Still invalid:<br/>handoff to a person"])
    X --> c1["Prompt injection or<br/>off-topic request"] --> c2(["Abstain: nothing runs,<br/>neutral answer, a person available"])
    X --> d1["The customer types a PIN<br/>or a card number"] --> d2(["Erased before saving or reaching the model;<br/>the customer is warned and offered a block"])
    X --> e1["Not identified,<br/>or the session expired"] --> e2["Secure form with a one-time code<br/>on every registered channel"] --> e3(["Identified: the confirmation is asked again.<br/>Cannot identify: handoff to a person"])
    X --> f1["A write<br/>times out"] --> f2["State is UNKNOWN: re-read by<br/>idempotency key, never a blind second write"] --> f3(["Found: the real case number is reported.<br/>Still unknown: handoff to a person"])
    X --> g1["The same message<br/>arrives twice"] --> g2(["Idempotent: one write, same result"])
    X --> h1["Unsupported<br/>language"] --> h2(["Answer in Spanish or Portuguese<br/>and say so"])
    X --> i1["Theft, scam or<br/>vulnerability mentioned"] --> i2(["Offer a block first,<br/>then a person with priority"])
    classDef persona fill:#127a4b,color:#fff,stroke:#0b5133
    classDef seguro fill:#4a1f73,color:#fff,stroke:#4a1f73
    class a4,b3,i2 persona
    class c2,d2,e3,f3,g2,h2 seguro
```

*Detail: `ARQUITECTURA.md` §7, `SEGURIDAD.md` and `PROCESOS.md`.*

## 4. Who decides what

| Decision | Model | Code | Person |
|---|---|---|---|
| What the customer meant, and in which language | ✔ describes it | validates it against a closed catalog | |
| Which transaction it is | the Comparator suggests an alias | checks it against the real list | the customer confirms |
| Whether an action is allowed | | ✔ pure function of verified facts | |
| Executing and verifying | | ✔ idempotent tool and re-read | |
| What the customer reads | ✔ writes it from verified facts | ✔ checks figures, actions and language | |
| Cases with risk, money at stake or doubt | | routes and prioritizes | ✔ decides |
