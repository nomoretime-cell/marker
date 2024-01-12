import configparser


class ConfigReader:
    def __init__(self, config_path: str) -> None:
        self.config_path: str = config_path
        self.config: configparser.ConfigParser = configparser.ConfigParser()
        self.config.read(self.config_path)

    def get_value(self, section: str, key: str) -> str:
        return self.config.get(section, key)
