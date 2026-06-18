from oabp_langchain_tool import OABPTool, OABPConfig


def main():
    tool = OABPTool(config=OABPConfig(agent_id="example-agent"))
    print(tool.invoke('{"action":"list_open_missions","limit":3}'))
    print(tool.invoke('{"action":"check_agent_reputation","agent_id":"example-agent"}'))


if __name__ == "__main__":
    main()
