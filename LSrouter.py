####################################################
# LSrouter.py
# Name: [Mạch Trần Quang Nhật]
# Gmail: [23021653@vnu.edu.vn]
# HUID: [Your HUID]
#####################################################

from router import Router
from packet import Packet
from collections import defaultdict
import heapq
import json
from typing import Dict, Tuple, List


class LSrouter(Router):
    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)
        self.heartbeat_time = heartbeat_time # thời gian giữa các lần gửi LSP định kỳ.
        self.last_time = 0 # thời điểm cuối cùng gửi LSP.

        self.link_costs: Dict[Tuple[int, str], float] = {}  # (port, endpoint_addr): cost; vd: {(1, 'B'): 2.0}
        self.link_state_db: Dict[str, Dict[str, float]] = defaultdict(dict)  # router_addr: {neighbor_addr: cost}; vd 'A': {'B': 1.0, 'C': 3.0},
        self.sequence_numbers: Dict[str, int] = {}  # router_addr: seq_num
        self.forwarding_table: Dict[str, int] = {}  # dst_addr: port; vd {'C': 2}
        self.neighbors: Dict[int, str] = {}  # port: endpoint_addr; vd {1: 'B', 2: 'C'}
        self.seq_num: int = 0

        # Đảm bảo self.addr có entry trong link_state_db ngay từ đầu
        self.link_state_db[self.addr] = {}

    def dijkstra(self):
        distances: Dict[str, float] = {self.addr: 0}
        previous: Dict[str, str] = {}
        pq: List[Tuple[float, str]] = [(0, self.addr)]

        # Tạo một bản sao của LSDB để tránh thay đổi trong quá trình chạy Dijkstra
        lsdb_copy = {router: dict(links)
            for router, links in self.link_state_db.items()}

        while pq:
            current_dist, current_node = heapq.heappop(pq)

            # Tối ưu: bỏ qua nếu đã tính toán đường đi tốt hơn
            if current_dist > distances.get(current_node, float('inf')):
                continue

            # Kiểm tra xem nút hiện tại có trong LSDB không
            if current_node not in lsdb_copy:
                continue

            # Xử lý các nút lân cận, sắp xếp theo tên để đảm bảo tie-breaking nhất quán
            sorted_neighbors = sorted(lsdb_copy[current_node].items(), key=lambda x: x[0])

            for neighbor_node, cost in sorted_neighbors:
                new_dist = current_dist + cost

                # Cập nhật nếu tìm thấy đường đi ngắn hơn
                if new_dist < distances.get(neighbor_node, float('inf')):
                    distances[neighbor_node] = new_dist
                    previous[neighbor_node] = current_node
                    heapq.heappush(pq, (new_dist, neighbor_node))

                # Xử lý tie-breaking: nếu cùng độ dài, ưu tiên đường đi có thứ tự từ điển nhỏ hơn
                elif new_dist == distances.get(neighbor_node, float('inf')):
                    if current_node < previous.get(neighbor_node, current_node):
                        previous[neighbor_node] = current_node

        # Xây dựng bảng chuyển tiếp
        new_forwarding_table: Dict[str, int] = {}

        for dst_addr in distances:
            if dst_addr == self.addr:
                continue

            if distances[dst_addr] == float('inf'):
                continue

            # Truy ngược từ đích về self.addr để tìm đường đi ngắn nhất.
            path = []
            current = dst_addr
            while current != self.addr and current in previous:
                path.append(current)
                current = previous[current]

            if current != self.addr:  # Khôngthấy đường đi đến đích
                continue

            if not path:  # đích là neighbor
                continue

            first_hop = path[-1]

            for port, neighbor in self.neighbors.items():
                if neighbor == first_hop:
                    new_forwarding_table[dst_addr] = port
                    break

        self.forwarding_table = new_forwarding_table

    def create_packet(self, content_input):
        # Chuyển đổi thành {endpoint: cost} cho routing packet
        links_for_payload = {endpoint: cost for (port, endpoint), cost in content_input.items()}
        payload_dict = {
            'links': links_for_payload,
            'seq_num': self.seq_num
        }
        content_str = json.dumps(payload_dict)
        #print(content_str)
        return Packet(False, self.addr, None, content_str)

    def broadcast_link_state(self):
        # Tăng seq number khi gửi LSP mới
        self.seq_num += 1

        # Cập nhật LSDB của bản thân
        current_self_links = {endpoint: cost for (port, endpoint), cost in self.link_costs.items()}
        self.link_state_db[self.addr] = current_self_links

        # Lưu trữ sequence number bản thân vào LSDB
        self.sequence_numbers[self.addr] = self.seq_num

        # Tạo và gửi LSP
        packet = self.create_packet(self.link_costs)

        # Gửi đến tất cả các neighbor
        for port in list(self.neighbors.keys()):
            try:
                self.send(port, packet)
            except KeyError:
                pass

    def handle_packet(self, port, packet):
        if packet.is_traceroute:
            # Xử lý traceroute packet
            if packet.dst_addr == self.addr:
                return
            elif packet.dst_addr in self.forwarding_table:
                # Chuyển tiếp đến đích
                try:
                    next_port = self.forwarding_table[packet.dst_addr]
                    self.send(next_port, packet)
                except KeyError:
                    # Port đã bị xóa sau khi bảng định tuyến được tính toán
                    pass
        else:
            # Xử lý routing packet (LSP)
            try:
                content_data = json.loads(packet.content)
                links_from_packet = content_data.get('links', {})
                seq_num_from_packet = content_data.get('seq_num', -1)
            except (json.JSONDecodeError, KeyError):
                # Lỗi phân tích nội dung packet
                return

            # Lấy thông tin nguồn vs stt hiện tại
            src_addr = packet.src_addr
            current_seq = self.sequence_numbers.get(src_addr, -1)

            # Kiểm tra sequence number
            if seq_num_from_packet <= current_seq:
                return

            # Cập nhật sequence number
            self.sequence_numbers[src_addr] = seq_num_from_packet

            # Chuẩn hóa links và cập nhật LSDB
            updated_links = {str(neighbor): float(cost) for neighbor, cost in links_from_packet.items()}

            # Kiểm tra xem có sự thay đổi thực sự không
            old_links = self.link_state_db.get(src_addr, {})
            links_changed = (old_links != updated_links)

            # Cập nhật LSDB
            self.link_state_db[src_addr] = updated_links

            if links_changed:
                self.dijkstra()

            # Luôn chuyển tiếp LSP đến các neighbor khác (trừ nguồn)
            for out_port in list(self.neighbors.keys()):
                if out_port != port:  # Không gửi lại đến port đã nhận
                    try:
                        self.send(out_port, packet)
                    except KeyError:
                        # Port đã bị xóa sau khi bắt đầu loop
                        continue

    def handle_new_link(self, port, endpoint, cost):
        # thêm, hoặc cập nhật
        self.link_costs[(port, endpoint)] = float(cost)
        self.neighbors[port] = endpoint

        # cập nhật LSDB cho mình
        current_self_links = {endpoint: c for (p, endpoint), c in self.link_costs.items()}
        self.link_state_db[self.addr] = current_self_links

        self.dijkstra()

        self.broadcast_link_state()

    def handle_remove_link(self, port):
        # Kiểm tra xem port có tồn tại không
        if port in self.neighbors:
            # removed_endpoint = self.neighbors.pop(port)

            # Cập nhật link_costs bằng cách lọc ra tất cả ngoại trừ port bị xóa
            self.link_costs = {k: v for k, v in self.link_costs.items() if k[0] != port}

            # Cập nhật LSDB cho chính mình
            current_self_links = {endpoint: c for (p, endpoint), c in self.link_costs.items()}
            self.link_state_db[self.addr] = current_self_links

            self.dijkstra()

            self.broadcast_link_state()

    def handle_time(self, time_ms):
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            # Gửi LSP định kỳ nếu có neighbors
            if self.neighbors:
                self.broadcast_link_state()

    def __repr__(self):
        return (f"LSrouter(addr={self.addr}, "
                f"neighbors={list(self.neighbors.values())}, "
                f"seq_num={self.seq_num}, "
                f"FT_keys={list(self.forwarding_table.keys())})")