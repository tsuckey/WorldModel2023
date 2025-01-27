import os
import argparse

import imageio
import numpy as np
import supersuit as ss
import torch
#from pettingzoo.mpe import simple_v3
from pettingzoo.atari import space_invaders_v2
from PIL import Image, ImageDraw

from agilerl.algorithms.matd3 import MATD3


# Define function to return image
def _label_with_episode_number(frame, episode_num):
    im = Image.fromarray(frame)

    drawer = ImageDraw.Draw(im)

    if np.mean(frame) < 128:
        text_color = (255, 255, 255)
    else:
        text_color = (0, 0, 0)
    drawer.text(
        (im.size[0] / 20, im.size[1] / 18), f"ep: {episode_num+1}", fill=text_color
    )

    return im


if __name__ == "__main__":

    #引数を取得
    parser = argparse.ArgumentParser()

    parser.add_argument('-dt', '--datetime', help='年月日時分をYYYYMMDD-hhmmの形式で指定。')

    args = parser.parse_args()

    if not args.datetime:
        parser.error('datetime が指定されていません。')

    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Configure the environment
    env = space_invaders_v2.parallel_env(
        full_action_space=False,
        max_cycles=10*1000*1000,
        render_mode="rgb_array"
    )
    
    channels_last = True  # Needed for environments that use images as observations
    if channels_last:
        # Environment processing for image based observations
        env = ss.frame_skip_v0(env, 4)
        env = ss.clip_reward_v0(env, lower_bound=-1, upper_bound=1)
        env = ss.color_reduction_v0(env, mode="B")
        env = ss.resize_v1(env, x_size=84, y_size=84)
        env = ss.frame_stack_v1(env, 4)
    env.reset()
    try:
        state_dim = [env.observation_space(agent).n for agent in env.agents]
        one_hot = True
    except Exception:
        state_dim = [env.observation_space(agent).shape for agent in env.agents]
        one_hot = False
    try:
        action_dim = [env.action_space(agent).n for agent in env.agents]
        discrete_actions = True
        max_action = None
        min_action = None
    except Exception:
        action_dim = [env.action_space(agent).shape[0] for agent in env.agents]
        discrete_actions = False
        max_action = [env.action_space(agent).high for agent in env.agents]
        min_action = [env.action_space(agent).low for agent in env.agents]

    # Pre-process image dimensions for pytorch convolutional layers
    if channels_last:
        state_dim = [
            (state_dim[2], state_dim[0], state_dim[1]) for state_dim in state_dim
        ]

    # Append number of agents and agent IDs to the initial hyperparameter dictionary
    n_agents = env.num_agents
    agent_ids = env.agents

    # Instantiate an MADDPG object
    matd3 = MATD3(
        state_dim,
        action_dim,
        one_hot,
        n_agents,
        agent_ids,
        max_action,
        min_action,
        discrete_actions,
        device=device,
    )

    # Load the saved algorithm into the MADDPG object
    #path = "./models/MATD3/MATD3_trained_agent.pt"
    path = "./result/"+args.datetime+"/MATD3_trained_agent.pt"
    matd3.loadCheckpoint(path)

    # Define test loop parameters
    episodes = 1  # Number of episodes to test agent on
    max_steps = 10*1000*1000  # Max number of steps to take in the environment in each episode

    rewards = []  # List to collect total episodic reward
    frames = []  # List to collect frames
    indi_agent_rewards = {
        agent_id: [] for agent_id in agent_ids
    }  # Dictionary to collect inidivdual agent rewards

    # Test loop for inference
    for ep in range(episodes):
        state, info = env.reset()
        agent_reward = {agent_id: 0 for agent_id in agent_ids}
        score = 0
        for i,_ in enumerate(range(max_steps)):
            if channels_last:
                state = {
                    agent_id: np.moveaxis(np.expand_dims(s, 0), [3], [1])
                    for agent_id, s in state.items()
                }

            agent_mask = info["agent_mask"] if "agent_mask" in info.keys() else None
            env_defined_actions = (
                info["env_defined_actions"]
                if "env_defined_actions" in info.keys()
                else None
            )

            # Get next action from agent
            cont_actions, discrete_action = matd3.getAction(
                state,
                epsilon=0,
                agent_mask=agent_mask,
                env_defined_actions=env_defined_actions,
            )
            if matd3.discrete_actions:
                action = discrete_action
            else:
                action = cont_actions

            # Save the frame for this step and append to frames list
            frame = env.render()
            frames.append(_label_with_episode_number(frame, episode_num=ep))

            # Take action in environment
            state, reward, termination, truncation, info = env.step(action)

            # Save agent's reward for this step in this episode
            for agent_id, r in reward.items():
                agent_reward[agent_id] += r

            # Determine total score for the episode and then append to rewards list
            score = sum(agent_reward.values())

            # Stop episode if any agents have terminated
            if any(truncation.values()) or any(termination.values()):
                print("terminated.")
                break

        rewards.append(score)
        print(i)

        # Record agent specific episodic reward
        for agent_id in agent_ids:
            indi_agent_rewards[agent_id].append(agent_reward[agent_id])

        print("-" * 15, f"Episode: {ep}", "-" * 15)
        print("Episodic Reward: ", rewards[-1])
        for agent_id, reward_list in indi_agent_rewards.items():
            print(f"{agent_id} reward: {reward_list[-1]}")
    env.close()

    # Save the gif to specified path
    #gif_path = "./videos/"
    gif_path = "./result/"+args.datetime
    #print(os.path.join(gif_path, "speaker_listener.gif"))
    os.makedirs(gif_path, exist_ok=True)
    imageio.mimwrite(
        #os.path.join("./videos/", "speaker_listener.gif"), frames, duration=10
        os.path.join(gif_path, "space_invaders_v2_"+str(i)+".gif"), frames, duration=5
    )

    print("Done.")