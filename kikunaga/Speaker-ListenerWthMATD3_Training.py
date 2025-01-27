"""
This tutorial shows how to train an MATD3 agent on the simple speaker listener multi-particle environment.

Authors: Michael (https://github.com/mikepratt1), Nickua (https://github.com/nicku-a)
"""

import os
import pprint
import datetime

import numpy as np
import torch
from pettingzoo.mpe import simple_speaker_listener_v4
from tqdm import trange

from agilerl.components.multi_agent_replay_buffer import MultiAgentReplayBuffer
from agilerl.hpo.mutation import Mutations
from agilerl.hpo.tournament import TournamentSelection
from agilerl.utils.utils import initialPopulation

if __name__ == "__main__":

    #現在日時を取得
    dt_now = datetime.datetime.now()
    str_dt_now = dt_now.strftime("%Y%m%d-%H%M")
    print(str_dt_now)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    #device = torch.device("mps")
    print("===== AgileRL Online Multi-Agent Demo =====")

    # Define the network configuration
    # ネットワークコンフィグレーションの定義
    NET_CONFIG = {
        "arch": "mlp",  # Network architecture
        "h_size": [32, 32],  # Actor hidden size
    }

    # Define the initial hyperparameters
    # 初期ハイパーパラメータの定義
    INIT_HP = {
        "POPULATION_SIZE": 4,
        "ALGO": "MATD3",  # Algorithm
        # Swap image channels dimension from last to first [H, W, C] -> [C, H, W]
        "CHANNELS_LAST": False,
        "BATCH_SIZE": 32,  # Batch size
        "LR": 0.01,  # Learning rate
        "GAMMA": 0.95,  # Discount factor
        "MEMORY_SIZE": 100000,  # Max memory buffer size
        "LEARN_STEP": 5,  # Learning frequency
        "TAU": 0.01,  # For soft update of target parameters
        "POLICY_FREQ": 2,  # Policy frequnecy
    }

    # Define the simple speaker listener environment as a parallel environment
    # シンプル・スピーカー・リスナー環境（並列）の定義
    env = simple_speaker_listener_v4.parallel_env(continuous_actions=True)
    env.reset()

    # Configure the multi-agent algo input arguments
    # マルチ・エージェントアルゴへの入力引数の設定
    try:
        state_dim = [env.observation_space(agent).n for agent in env.agents]
        one_hot = True
    except Exception:
        state_dim = [env.observation_space(agent).shape for agent in env.agents]
        one_hot = False
    try:
        action_dim = [env.action_space(agent).n for agent in env.agents]
        INIT_HP["DISCRETE_ACTIONS"] = True
        INIT_HP["MAX_ACTION"] = None
        INIT_HP["MIN_ACTION"] = None
    except Exception:
        action_dim = [env.action_space(agent).shape[0] for agent in env.agents]
        INIT_HP["DISCRETE_ACTIONS"] = False
        INIT_HP["MAX_ACTION"] = [env.action_space(agent).high for agent in env.agents]
        INIT_HP["MIN_ACTION"] = [env.action_space(agent).low for agent in env.agents]

    
    if False: # デバッグ出力
        print("state_dim", state_dim)
        print("one_hot", one_hot)
        print( 'INIT_HP["DISCRETE_ACTIONS"]', INIT_HP["DISCRETE_ACTIONS"])
        print( 'INIT_HP["MAX_ACTION"]', INIT_HP["MAX_ACTION"])
        print( 'INIT_HP["MIN_ACTION"]', INIT_HP["MIN_ACTION"])
    

    # Not applicable to MPE environments, used when images are used for observations (Atari environments)
    # MPE環境には適用されない。観測のために画像が使用される場合に使う（アタリ環境）
    if INIT_HP["CHANNELS_LAST"]:
        state_dim = [
            (state_dim[2], state_dim[0], state_dim[1]) for state_dim in state_dim
        ]

    # Append number of agents and agent IDs to the initial hyperparameter dictionary
    # エージェントとエージェントIDの数を、ハイパーパラメータディクショナリの初期化のために加える
    INIT_HP["N_AGENTS"] = env.num_agents
    INIT_HP["AGENT_IDS"] = env.agents

    
    if True: # デバッグ出力
        print('state_dim', state_dim)
        print('action_dim', action_dim)
        print('one_hot', one_hot)
        print('NET_CONFIG')
        pprint.pprint(NET_CONFIG)
        print('INIT_HP')
        pprint.pprint(INIT_HP)
        print('device', device)
    
    # Create a population ready for evolutionary hyper-parameter optimisation
    # 進化的なハイパーパラメータ最適化のための母集団を作成する
    population = initialPopulation(
        INIT_HP["ALGO"],
        state_dim,
        action_dim,
        one_hot,
        NET_CONFIG,
        INIT_HP,
        population_size=INIT_HP["POPULATION_SIZE"],
        device=device,
    )

    # Configure the multi-agent replay buffer
    # マルチ・エージェント・リプレイバッファを設定する
    field_names = ["state", "action", "reward", "next_state", "done"]
    memory = MultiAgentReplayBuffer(
        INIT_HP["MEMORY_SIZE"],
        field_names=field_names,
        agent_ids=INIT_HP["AGENT_IDS"],
        device=device,
    )

    # Instantiate a tournament selection object (used for HPO)
    # トーナメント選択オブジェクトのインスタンス化（HPOで使用）
    tournament = TournamentSelection(
        tournament_size=2,  # Tournament selection size
        elitism=True,  # Elitism in tournament selection
        population_size=INIT_HP["POPULATION_SIZE"],  # Population size
        evo_step=1,
    )  # Evaluate using last N fitness scores

    # Instantiate a mutations object (used for HPO)
    # ミューテーション・オブジェクトのインスタンス化（HPOで使用）
    mutations = Mutations(
        algo=INIT_HP["ALGO"],
        no_mutation=0.2,  # Probability of no mutation
        architecture=0.2,  # Probability of architecture mutation
        new_layer_prob=0.2,  # Probability of new layer mutation
        parameters=0.2,  # Probability of parameter mutation
        activation=0,  # Probability of activation function mutation
        rl_hp=0.2,  # Probability of RL hyperparameter mutation
        rl_hp_selection=[
            "lr",
            "learn_step",
            "batch_size",
        ],  # RL hyperparams selected for mutation
        mutation_sd=0.1,  # Mutation strength
        agent_ids=INIT_HP["AGENT_IDS"],
        arch=NET_CONFIG["arch"],
        rand_seed=2,#1,
        device=device,
    )

    # Define training loop parameters
    # 学習ループ・パラメータを定義
    max_episodes = 5000 #500  # Total episodes (default: 6000)
    max_steps = 100 #25  # Maximum steps to take in each episode
    epsilon = 1.0  # Starting epsilon value
    eps_end = 0.1  # Final epsilon value
    eps_decay = 0.995  # Epsilon decay
    evo_epochs = 20  # Evolution frequency
    evo_loop = 1  # Number of evaluation episodes
    elite = population[0]  # Assign a placeholder "elite" agent

    # Training loop
    # 学習ループ
    for idx_epi in trange(max_episodes):
        
        for agent in population:  # Loop through population
            
            state, info = env.reset()  # Reset environment at start of episode
            agent_reward = {agent_id: 0 for agent_id in env.agents}
            if INIT_HP["CHANNELS_LAST"]:
                state = {
                    agent_id: np.moveaxis(np.expand_dims(s, 0), [-1], [-3])
                    for agent_id, s in state.items()
                }

            for _ in range(max_steps):
                agent_mask = info["agent_mask"] if "agent_mask" in info.keys() else None
                env_defined_actions = (
                    info["env_defined_actions"]
                    if "env_defined_actions" in info.keys()
                    else None
                )

                # Get next action from agent
                # エージェントから次の行動を取得する
                cont_actions, discrete_action = agent.getAction(
                    state, epsilon, agent_mask, env_defined_actions
                )
                if agent.discrete_actions:
                    action = discrete_action
                else:
                    action = cont_actions

                next_state, reward, termination, truncation, info = env.step(
                    action
                )  # Act in environment

                # Image processing if necessary for the environment
                # 環境に応じた画像処理を行う
                if INIT_HP["CHANNELS_LAST"]:
                    state = {agent_id: np.squeeze(s) for agent_id, s in state.items()}
                    next_state = {
                        agent_id: np.moveaxis(ns, [-1], [-3])
                        for agent_id, ns in next_state.items()
                    }

                # Save experiences to replay buffer
                # 経験をリプレイバッファに保存する
                memory.save2memory(state, cont_actions, reward, next_state, termination)

                # Collect the reward
                # 報酬を受け取る
                for agent_id, r in reward.items():
                    agent_reward[agent_id] += r

                # Learn according to learning frequency
                # 学習周期に合わせて学習する
                if (memory.counter % agent.learn_step == 0) and (
                    len(memory) >= agent.batch_size
                ):
                    experiences = memory.sample(
                        agent.batch_size
                    )  # Sample replay buffer
                    agent.learn(experiences)  # Learn according to agent's RL algorithm

                # Update the state
                # 状態を更新する
                if INIT_HP["CHANNELS_LAST"]:
                    next_state = {
                        agent_id: np.expand_dims(ns, 0)
                        for agent_id, ns in next_state.items()
                    }
                state = next_state

                # Stop episode if any agents have terminated
                # いずれかのエージェントが終了したならば、エピソードを停止する
                if any(truncation.values()) or any(termination.values()):
                    break

            # Save the total episode reward
            # エピソードの合計報酬を保存する
            score = sum(agent_reward.values())
            agent.scores.append(score)

        # Update epsilon for exploration
        # 探索用のイプシロンを更新
        epsilon = max(eps_end, epsilon * eps_decay)

        # Now evolve population if necessary
        # 必要であれば、母集団を進化させる
        if (idx_epi + 1) % evo_epochs == 0:
            # Evaluate population
            fitnesses = [
                agent.test(
                    env,
                    swap_channels=INIT_HP["CHANNELS_LAST"],
                    max_steps=max_steps,
                    loop=evo_loop,
                )
                for agent in population
            ]

            print(f"Episode {idx_epi + 1}/{max_episodes}")
            print(f'Fitnesses: {["%.2f" % fitness for fitness in fitnesses]}')
            print(
                f'100 fitness avgs: {["%.2f" % np.mean(agent.fitness[-100:]) for agent in population]}'
            )

            # Tournament selection and population mutation
            # トーナメント選択と母集団の変異
            elite, population = tournament.select(population)
            population = mutations.mutation(population)

    # Save the trained algorithm
    # 学習アルゴリズムを保存する
    path = "./models/MATD3"
    #path = "./"+str_dt_now+"/models/MATD3"
    filename = "MATD3_trained_agent.pt"
    filename = f"MATD3_trained_agent_{str_dt_now}.pt"
    os.makedirs(path, exist_ok=True)
    save_path = os.path.join(path, filename)
    elite.saveCheckpoint(save_path)

