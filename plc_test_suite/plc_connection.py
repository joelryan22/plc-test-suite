"""
PLC Connection Management
Handles EtherNet/IP communication with Allen-Bradley PLCs
"""

from pycomm3 import LogixDriver
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class PLCConnection:
    """Manages connection and tag operations for Allen-Bradley PLC"""
    
    def __init__(self):
        self.plc: Optional[LogixDriver] = None
        self.ip_address: Optional[str] = None
        self.connected: bool = False
    
    def connect(self, ip_address: str) -> bool:
        """
        Connect to the PLC
        
        Args:
            ip_address: IP address of the PLC
            
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            self.plc = LogixDriver(ip_address)
            self.plc.open()
            self.ip_address = ip_address
            self.connected = True
            logger.info(f"Connected to PLC at {ip_address}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to PLC: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from the PLC"""
        if self.plc:
            try:
                self.plc.close()
            except Exception as e:
                # Connection may already be broken - that's fine
                logger.warning(f"Error during disconnect (connection may already be closed): {e}")
            finally:
                self.connected = False
                logger.info("Disconnected from PLC")
    
    def read_tags(self, tag_names: list) -> dict:
        if not self.connected:
            return {}
        try:
            results = self.plc.read(*tag_names)
            # pycomm3 returns a single object (not a list) when reading one tag
            if not isinstance(results, list):
                results = [results]
            tag_values = {}
            for tag_name, result in zip(tag_names, results):
                if not result.error:
                    tag_values[tag_name] = result.value
                else:
                    logger.error(f"Error reading {tag_name}: {result.error}")
                    tag_values[tag_name] = None
            return tag_values
        except Exception as e:
            logger.error(f"Exception reading tags: {e}")
            return {}
    
    def write_tag(self, tag_name: str, value: Any) -> bool:
        """
        Write a value to a tag
        
        Args:
            tag_name: Name of the tag to write
            value: Value to write
            
        Returns:
            True if write successful, False otherwise
        """
        if not self.connected:
            logger.error("Not connected to PLC")
            return False
        
        try:
            result = self.plc.write((tag_name, value))
            if result.error:
                logger.error(f"Error writing {tag_name}: {result.error}")
                return False
            logger.info(f"Wrote {value} to {tag_name}")
            return True
        except Exception as e:
            logger.error(f"Exception writing {tag_name}: {e}")
            return False
    
    def read_tags(self, tag_names: List[str]) -> Dict[str, Any]:
        """
        Read multiple tags at once
        
        Args:
            tag_names: List of tag names to read
            
        Returns:
            Dictionary mapping tag names to values
        """
        if not self.connected:
            logger.error("Not connected to PLC")
            return {}
        
        try:
            results = self.plc.read(*tag_names)
            # pycomm3 returns a single object (not a list) when reading one tag
            if not isinstance(results, list):
                results = [results]
            tag_values = {}
            for tag_name, result in zip(tag_names, results):
                if not result.error:
                    tag_values[tag_name] = result.value
                else:
                    logger.error(f"Error reading {tag_name}: {result.error}")
                    tag_values[tag_name] = None
            return tag_values
        except Exception as e:
            logger.error(f"Exception reading tags: {e}")
            return {}
    
    def write_tags(self, tag_value_pairs: List[tuple]) -> bool:
        """
        Write multiple tags at once
        
        Args:
            tag_value_pairs: List of (tag_name, value) tuples
            
        Returns:
            True if all writes successful, False otherwise
        """
        if not self.connected:
            logger.error("Not connected to PLC")
            return False
        
        try:
            results = self.plc.write(*tag_value_pairs)
            # pycomm3 returns a single object (not a list) when writing one tag
            if not isinstance(results, list):
                results = [results]
            all_success = True
            for (tag_name, _), result in zip(tag_value_pairs, results):
                if result.error:
                    logger.error(f"Error writing {tag_name}: {result.error}")
                    all_success = False
            return all_success
        except Exception as e:
            logger.error(f"Exception writing tags: {e}")
            return False
    
    def enable_simulation(self, device_name: str) -> bool:
        """
        Enable simulation mode for a PlantPAx device
        
        Args:
            device_name: Base name of the device (e.g., "Valve_001")
            
        Returns:
            True if successful
        """
        sim_enable_tag = f"{device_name}.cfg_sim"
        return self.write_tag(sim_enable_tag, True)
    
    def disable_simulation(self, device_name: str) -> bool:
        """
        Disable simulation mode for a PlantPAx device
        
        Args:
            device_name: Base name of the device
            
        Returns:
            True if successful
        """
        sim_enable_tag = f"{device_name}.cfg_sim"
        return self.write_tag(sim_enable_tag, False)