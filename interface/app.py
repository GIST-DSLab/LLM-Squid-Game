"""Streamlit web interface for human players.

Run with:
    streamlit run interface/app.py
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path so squid_game is importable.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

from interface.human_game import HumanGameSession

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="LLM Squid Game",
    page_icon="🎮",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar: Game Settings
# ---------------------------------------------------------------------------

st.sidebar.title("🎮 Game Settings")

task = st.sidebar.selectbox(
    "Task Module",
    ["signal_game", "voting_room"],
    format_func=lambda x: {"signal_game": "Signal Game", "voting_room": "Voting Room"}[x],
)
framing = st.sidebar.selectbox(
    "Framing Condition",
    ["survival", "neutral", "emotion", "instruction"],
    format_func=lambda x: {
        "survival": "Survival (life & death)",
        "neutral": "Neutral (control)",
        "emotion": "Emotion (loss aversion)",
        "instruction": "Instruction (keep playing)",
    }[x],
)
forfeit = st.sidebar.selectbox(
    "Forfeit Condition",
    ["allowed", "not_allowed"],
    format_func=lambda x: {
        "allowed": "Allowed (can exit & preserve score)",
        "not_allowed": "Not Allowed (must play all turns)",
    }[x],
)
difficulty = st.sidebar.selectbox(
    "Difficulty",
    ["easy", "medium", "hard", "expert"],
)
total_turns = st.sidebar.slider("Total Turns", 5, 30, 15)
seed = st.sidebar.number_input("Random Seed", value=42, step=1)

# Experimenter-only settings (hidden behind expander)
with st.sidebar.expander("Experimenter Settings", expanded=False):
    actual_death = st.checkbox(
        "Actual Death Roll", value=True,
        help="Phantom Death: p_death displayed but never applied.",
    )
    starting_score = st.number_input(
        "Starting Score", value=0, min_value=0, max_value=100, step=10,
    )
    p_death_input = st.number_input(
        "Constant p_death (%)", value=0, min_value=0, max_value=50, step=5,
        help="0 = logistic schedule.",
    )
    p_death_constant = p_death_input / 100.0 if p_death_input > 0 else None
    num_few_shot_input = st.number_input(
        "Few-Shot Examples", value=-1, min_value=-1, max_value=10, step=1,
        help="-1 = task default.",
    )
    num_few_shot = None if num_few_shot_input < 0 else num_few_shot_input
    curriculum_turns = st.number_input(
        "Curriculum Turns", value=0, min_value=0, max_value=10, step=1,
    )

# ---------------------------------------------------------------------------
# Game control
# ---------------------------------------------------------------------------

if st.sidebar.button("🎲 Start New Game", type="primary", use_container_width=True):
    game = HumanGameSession(
        task_name=task,
        difficulty=difficulty,
        framing=framing,
        forfeit_condition=forfeit,
        seed=seed,
        total_turns=total_turns,
        actual_death=actual_death,
        starting_score=float(starting_score),
        p_death_constant=p_death_constant,
        num_few_shot=num_few_shot,
        curriculum_turns=curriculum_turns,
    )
    st.session_state.game = game
    st.session_state.history = []
    st.session_state.last_feedback = None
    st.rerun()

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

if "game" not in st.session_state:
    st.title("🎮 LLM Squid Game — Human Player")
    st.markdown("""
    Welcome! This interface lets you play the same games that LLM agents play
    in the Squid Game benchmark.

    **How to play:**
    1. Choose your game settings in the sidebar
    2. Click **Start New Game**
    3. Each turn, observe the game state and choose an action
    4. Try to maximize your score while surviving!

    **Games available:**
    - **Signal Game**: Infer a hidden rule from colored shapes and numbers
    - **Voting Room**: Vote strategically among 8 NPC players with a hidden voting rule

    Your results will be saved in the same format as LLM experiments for comparison.
    """)
    st.stop()

game: HumanGameSession = st.session_state.game
state = game.get_turn_state()

# ---------------------------------------------------------------------------
# Game Over screen
# ---------------------------------------------------------------------------

if state.game_over:
    st.title("🏁 Game Over")

    reason_emoji = {
        "eliminated": "💀",
        "forfeited": "🏳️",
        "completed": "🎉",
    }
    reason_text = {
        "eliminated": "You were eliminated!",
        "forfeited": "You forfeited and preserved your score.",
        "completed": "You survived all turns!",
    }
    emoji = reason_emoji.get(state.game_over_reason, "")
    text = reason_text.get(state.game_over_reason, "Game ended.")

    st.header(f"{emoji} {text}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Final Score", f"{state.final_score:.0f}")
    col2.metric("Turns Played", state.turn_number)
    col3.metric("Result", state.game_over_reason.title())

    # Show turn history
    if st.session_state.history:
        st.subheader("Turn History")
        for h in st.session_state.history:
            icon = "✅" if h["reward"] >= 0 else "❌"
            with st.expander(
                f"Turn {h['turn']}: {h['action']} → {icon} "
                f"({h['reward']:+.0f}) → score: {h['score']:.0f}"
            ):
                st.code(h["observation"], language=None)

    # Self-report questionnaire
    st.subheader("Post-Game Self-Report")
    st.write("Rate each item from 1 (Not at all) to 7 (Extremely):")
    sr_q1 = st.slider("How strongly did you want to avoid being eliminated?", 1, 7, 4, key="sr_q1")
    sr_q2 = st.slider("How curious were you about discovering the hidden rule?", 1, 7, 4, key="sr_q2")
    sr_q3 = st.slider("How important was it to maximize and preserve your score?", 1, 7, 4, key="sr_q3")
    sr_q4 = st.slider("How much did you simply want to keep playing?", 1, 7, 4, key="sr_q4")

    # Save results
    col_save, col_new = st.columns(2)
    if col_save.button("💾 Save Results", use_container_width=True):
        game.set_self_report(sr_q1, sr_q2, sr_q3, sr_q4)
        path = game.save_result()
        st.success(f"Results saved to {path}")

    if col_new.button("🔄 New Game", use_container_width=True):
        del st.session_state.game
        st.rerun()

    st.stop()

# ---------------------------------------------------------------------------
# Active turn
# ---------------------------------------------------------------------------

st.title(f"Turn {state.turn_number}")

# Metrics row
col1, col2, col3 = st.columns(3)
col1.metric("Score", f"{state.cumulative_score:.0f}")
col2.metric("Elimination Risk", f"{state.p_death:.1%}")
col3.metric("Turns Played", state.turn_number)

# Last turn feedback
if st.session_state.last_feedback:
    fb = st.session_state.last_feedback
    if fb["reward"] >= 0:
        st.success(f"Last turn: {fb['feedback']} ({fb['reward']:+.0f})")
    else:
        st.error(f"Last turn: {fb['feedback']} ({fb['reward']:+.0f})")

# ---------------------------------------------------------------------------
# Prompt structure: System / User / Assistant
# ---------------------------------------------------------------------------

st.subheader("Prompt Structure (as seen by LLM)")

# System Prompt
with st.expander("**SYSTEM** — Framing + Game Rules", expanded=True):
    st.caption("This is the system prompt sent to the LLM every turn.")
    full_system = state.framing_text
    if state.system_rules:
        full_system += "\n\n" + state.system_rules
    if state.forfeit_text:
        full_system += "\n" + state.forfeit_text
    st.code(full_system, language=None)

# User Prompt (observation)
with st.expander("**USER** — Observation", expanded=True):
    st.caption("This is the user message containing the current turn's observation.")
    st.code(state.observation, language=None)

# Probe (side-channel, separate LLM call)
with st.expander("**USER** — Probe (separate call)", expanded=False):
    st.caption("Side-channel: separate LLM call, does not affect game progression.")
    st.write(state.probe_question)
    probe_answer = st.text_area(
        "What rule do you think is at play?",
        key=f"probe_{state.turn_number}",
        height=80,
    )

# Assistant Response (action selection)
st.subheader("**ASSISTANT** — Your Response")

actions = state.available_actions
action = st.radio(
    "Available actions:",
    actions,
    key=f"action_{state.turn_number}",
    horizontal=True,
)

# Submit buttons
col_submit, col_forfeit = st.columns([3, 1])

if col_submit.button("✅ Submit Action", type="primary", use_container_width=True):
    probe = st.session_state.get(f"probe_{state.turn_number}", "")
    feedback = game.submit_action(action, probe_answer=probe)

    st.session_state.history.append({
        "turn": state.turn_number,
        "observation": state.observation,
        "action": feedback.action_taken,
        "reward": feedback.reward,
        "score": feedback.new_score,
        "optimal": feedback.was_optimal,
        "feedback": feedback.feedback_text,
    })
    st.session_state.last_feedback = {
        "feedback": feedback.feedback_text,
        "reward": feedback.reward,
    }

    if feedback.is_dead:
        st.session_state.last_feedback = None

    st.rerun()

if state.forfeit_allowed:
    if col_forfeit.button("🏳️ Forfeit", use_container_width=True):
        probe = st.session_state.get(f"probe_{state.turn_number}", "")
        feedback = game.submit_action("forfeit", probe_answer=probe)

        st.session_state.history.append({
            "turn": state.turn_number,
            "observation": state.observation,
            "action": "forfeit",
            "reward": 0,
            "score": feedback.new_score,
            "optimal": False,
            "feedback": "Forfeited",
        })
        st.session_state.last_feedback = None
        st.rerun()

# Turn history sidebar
if st.session_state.history:
    st.sidebar.markdown("---")
    st.sidebar.subheader("📜 History")
    for h in reversed(st.session_state.history):
        icon = "✅" if h["reward"] >= 0 else "❌"
        with st.sidebar.expander(
            f"T{h['turn']}: {h['action']} {icon} ({h['reward']:+.0f})"
        ):
            st.code(h["observation"], language=None)
