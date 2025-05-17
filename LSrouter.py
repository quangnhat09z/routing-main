####################################################
# LSrouter.py
# Name: [Your name]
# HUID: [Your HUID]
#####################################################

from router import Router
from packet import Packet
from collections import defaultdict
import heapq
import json
from typing import Dict, Tuple, List


class LSrouter(Router):
    # ... (phần __init__ và các hàm khác giữ nguyên như bạn đã sửa lỗi TypeError) ...
    # Ví dụ, create_packet và handle_packet phải đúng như phiên bản đã sửa lỗi TypeError.

    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)
        #self.heartbeat_time = heartbeat_time
        self.heartbeat_time = float('inf')  # Tạm thời vô hiệu hóa heartbeat

        self.last_time = 0
        self.link_costs: Dict[Tuple[int, str], float] = {}  # (port, endpoint_addr): cost
        self.link_state_db: Dict[str, Dict[str, float]] = defaultdict(dict)  # router_addr: {neighbor_addr: cost}
        self.sequence_numbers: Dict[str, int] = {}  # router_addr: seq_num
        self.forwarding_table: Dict[str, int] = {}  # dst_addr: port
        self.neighbors: Dict[int, str] = {}  # port: endpoint_addr
        self.seq_num: int = 0

        # Quan trọng: Đảm bảo self.addr có entry trong link_state_db ngay từ đầu nếu cần
        # Hoặc, nó sẽ được tạo khi link đầu tiên được thêm.
        # self.link_state_db[self.addr] = {} # Khởi tạo để self.addr luôn là một key

    def create_packet(self, content_input, is_traceroute=False):
        kind = Packet.TRACEROUTE if is_traceroute else Packet.ROUTING
        links_for_payload = {}
        if not is_traceroute:
            # content_input là self.link_costs = {(port, endpoint): cost}
            # Chuyển đổi thành {endpoint: cost}
            links_for_payload = {endpoint: cost for (port, endpoint), cost in content_input.items()}
        else:
            links_for_payload = content_input

        payload_dict = {
            'links': links_for_payload,
            'seq_num': self.seq_num if not is_traceroute else 0  # traceroute không cần seq_num thực sự
        }
        content_str = json.dumps(payload_dict)
        return Packet(kind, self.addr, None, content_str)

    def dijkstra(self):
        distances: Dict[str, float] = {self.addr: 0}
        previous: Dict[str, str] = {}
        pq: List[Tuple[float, str]] = [(0, self.addr)]

        while pq:
            current_dist, current_node = heapq.heappop(pq)

            if current_dist > distances.get(current_node, float('inf')):
                continue

            if current_node not in self.link_state_db:  # current_node có thể là client hoặc router chưa gửi LSP
                continue

            # Sắp xếp các neighbor theo tên để đảm bảo thứ tự xử lý nhất quán (Hỗ trợ tie-breaking)
            # self.link_state_db[current_node] là một dict {neighbor_addr: cost}
            # .items() trả về list các tuple (neighbor_addr, cost)
            # sorted() sẽ sắp xếp dựa trên phần tử đầu tiên của tuple (tên neighbor)
            sorted_neighbors_items = sorted(self.link_state_db[current_node].items())

            for neighbor_node, cost in sorted_neighbors_items:  # Duyệt theo thứ tự đã sắp xếp
                new_dist = current_dist + cost
                if new_dist < distances.get(neighbor_node, float('inf')):
                    distances[neighbor_node] = new_dist
                    previous[neighbor_node] = current_node
                    heapq.heappush(pq, (new_dist, neighbor_node))

        # Phần xây dựng forwarding_table giữ nguyên
        new_forwarding_table: Dict[str, int] = {}
        # ... (logic xây dựng forwarding_table như trước) ...
        for dst_addr in distances:
            if dst_addr == self.addr or distances[dst_addr] == float('inf'):
                continue
            path_tracer_node = dst_addr
            while path_tracer_node in previous and previous[path_tracer_node] != self.addr:
                path_tracer_node = previous[path_tracer_node]

            if path_tracer_node == self.addr:  # Should not happen if dst_addr is reachable and not self
                continue

            found_port_for_first_hop = False
            for port_num, neighbor_endpoint in self.neighbors.items():
                if neighbor_endpoint == path_tracer_node:
                    new_forwarding_table[dst_addr] = port_num
                    found_port_for_first_hop = True
                    break
            # Optional: Add a warning if port not found, though it shouldn't happen with correct logic
            # if not found_port_for_first_hop and path_tracer_node in distances and distances[path_tracer_node] != float('inf'):
            #    print(f"Router {self.addr}: WARNING - No port found for first hop {path_tracer_node} to dst {dst_addr}")

        self.forwarding_table = new_forwarding_table

    def broadcast_link_state(self):
        self.seq_num += 1
        # self.link_costs chứa {(port, endpoint): cost}
        # create_packet sẽ chuyển nó thành {endpoint: cost} cho payload
        packet_content = self.link_costs
        packet = self.create_packet(packet_content, is_traceroute=False)
        for port in self.neighbors:  # self.neighbors là {port: endpoint_addr}
            try:
                self.send(port, packet)
            except KeyError:  # Port có thể không còn hợp lệ nếu link vừa bị xóa
                continue

    def handle_packet(self, port, packet):
        # Giả sử bạn có một cách để truy cập thời gian mô phỏng hiện tại, ví dụ: self.network_time_ms
        # Nếu không, bạn có thể bỏ qua phần [TIME_MS] hoặc tìm cách truyền nó vào.
        # Trong nhiều framework mô phỏng, thời gian được truyền vào hàm handle_time,
        # nhưng không trực tiếp vào handle_packet. Bạn có thể cần lưu nó từ handle_time.
        # Hoặc, nếu network.py gọi handle_packet, nó có thể truyền thời gian.
        # Hiện tại, tôi sẽ để placeholder [TIME_MS].

        if packet.is_traceroute:
            if packet.dst_addr in self.forwarding_table:
                try:
                    self.send(self.forwarding_table[packet.dst_addr], packet)
                except KeyError:
                    pass
        else:  # Routing packet
            try:
                content_data = json.loads(packet.content)
                links_from_packet = content_data['links']
                seq_num_from_packet = content_data['seq_num']
            except (json.JSONDecodeError, KeyError) as e:
                # In lỗi nếu có vấn đề với gói tin để biết nó là gì
                print(
                    f"ROUTER {self.addr} [TIME_MS]: ERROR decoding packet from port {port}. Content: '{packet.content}'. Error: {e}")
                return

            src_addr = packet.src_addr

            # Log trước khi kiểm tra sequence number
            print(
                f"ROUTER {self.addr} [TIME_MS]: Received ROUTING packet from {src_addr} on port {port}. Seq_rcvd={seq_num_from_packet}. Links_in_pkt={links_from_packet}. Current_stored_seq_for_src={self.sequence_numbers.get(src_addr, 'None')}")

            if src_addr not in self.sequence_numbers or \
                    seq_num_from_packet > self.sequence_numbers.get(src_addr,
                                                                    -1):  # -1 để đảm bảo seq 0 được chấp nhận nếu chưa có

                print(
                    f"  ROUTER {self.addr} [TIME_MS]: ACCEPTED NEW LSP from {src_addr}. Old_stored_seq={self.sequence_numbers.get(src_addr, 'None')}, New_seq={seq_num_from_packet}.")

                self.sequence_numbers[src_addr] = seq_num_from_packet

                # Cập nhật link_state_db[src_addr] với thông tin từ LSP mới
                # Đảm bảo keys là string và values là float
                updated_links_for_src = {
                    str(neighbor): float(cost)
                    for neighbor, cost in links_from_packet.items()
                }

                # Dòng if not links_from_packet: self.link_state_db[src_addr] = {} là thừa
                # vì dictionary comprehension ở trên đã xử lý trường hợp rỗng.
                # Nó sẽ gán một dict rỗng nếu links_from_packet rỗng.
                self.link_state_db[src_addr] = updated_links_for_src

                print(
                    f"  ROUTER {self.addr} [TIME_MS]: Updated LSA for {src_addr} in local DB: {self.link_state_db[src_addr]}")

                # Vì link_state_db đã thay đổi, chạy lại Dijkstra
                print(f"  ROUTER {self.addr} [TIME_MS]: Running Dijkstra due to LSP from {src_addr}...")
                self.dijkstra()  # Hàm dijkstra của bạn cũng nên có log về kết quả FT nếu cần
                print(
                    f"  ROUTER {self.addr} [TIME_MS]: Dijkstra FINISHED. New Forwarding Table: {self.forwarding_table}")

                # Quảng bá LSP này đến các neighbor khác
                # Sử dụng list để tránh lỗi nếu self.neighbors thay đổi trong lúc lặp
                neighbor_ports = list(self.neighbors.keys())
                if neighbor_ports:  # Chỉ flood nếu có neighbor
                    print(
                        f"  ROUTER {self.addr} [TIME_MS]: Flooding LSP from {src_addr} (seq {seq_num_from_packet}) to neighbors: {neighbor_ports} (excluding port {port})")
                    for out_port in neighbor_ports:
                        if out_port != port:  # Không gửi lại cổng vừa nhận
                            try:
                                # print(f"    ROUTER {self.addr} [TIME_MS]: Flooding to port {out_port}") # Log chi tiết hơn nếu cần
                                self.send(out_port, packet)  # Gửi gói tin gốc
                            except KeyError:
                                print(
                                    f"    ROUTER {self.addr} [TIME_MS]: ERROR - Failed to flood to port {out_port} (KeyError, port likely removed).")
                                continue  # Bỏ qua nếu port không còn hợp lệ
                else:
                    print(f"  ROUTER {self.addr} [TIME_MS]: No neighbors to flood LSP from {src_addr}.")

            else:  # LSP cũ hoặc có sequence number bằng
                print(
                    f"  ROUTER {self.addr} [TIME_MS]: REJECTED/OLD LSP from {src_addr}. Seq_rcvd={seq_num_from_packet}, Stored_seq={self.sequence_numbers.get(src_addr, 'None')}.")

    def handle_new_link(self, port, endpoint, cost):
        print(f"ROUTER {self.addr} TIME [TIME]: handle_new_link(port={port}, ep={endpoint}, cost={cost}) CALLED.")
        print(
            f"  BEFORE: neighbors={self.neighbors}, link_costs={self.link_costs}, lsa_self={self.link_state_db.get(self.addr)}")

        # ... (code hiện tại của bạn) ...
        self.link_costs[(port, endpoint)] = float(cost)
        self.neighbors[port] = endpoint
        current_self_links = {ep: c for (p, ep), c in self.link_costs.items()}
        self.link_state_db[self.addr] = current_self_links

        print(
            f"  AFTER: neighbors={self.neighbors}, link_costs={self.link_costs}, lsa_self={self.link_state_db.get(self.addr)}")

        self.dijkstra()
        print(f"  AFTER DIJKSTRA: forwarding_table={self.forwarding_table}")
        self.broadcast_link_state()  # broadcast_link_state cũng nên có log về seq_num và nội dung gửi đi
        self.broadcast_link_state()

    def handle_remove_link(self, port):
        print(f"ROUTER {self.addr} TIME [TIME]: handle_remove_link(port={port}) CALLED.")
        if port in self.neighbors:
            # ... (in trạng thái BEFORE tương tự như trên) ...
            print(
                f"  BEFORE: port_to_remove={port}, current_neighbor_at_port={self.neighbors.get(port)}, neighbors={self.neighbors}, link_costs={self.link_costs}, lsa_self={self.link_state_db.get(self.addr)}")

            removed_endpoint = self.neighbors.pop(port)
            self.link_costs = {k_tuple: v_cost for k_tuple, v_cost in self.link_costs.items() if k_tuple[0] != port}
            current_self_links = {ep: c for (p, ep), c in self.link_costs.items()}
            self.link_state_db[self.addr] = current_self_links

            print(
                f"  AFTER: removed_ep={removed_endpoint}, neighbors={self.neighbors}, link_costs={self.link_costs}, lsa_self={self.link_state_db.get(self.addr)}")

            self.dijkstra()
            print(f"  AFTER DIJKSTRA: forwarding_table={self.forwarding_table}")
            self.broadcast_link_state()

    def handle_time(self, time_ms):
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            # Nếu không có neighbor nào, không cần broadcast
            if self.neighbors:
                self.broadcast_link_state()

    # def handle_time(self, time_ms):
    #     """Handle current time."""
    #     if time_ms - self.last_time >= self.heartbeat_time:
    #         self.last_time = time_ms
    #         # Luôn cố gắng broadcast link state.
    #         # broadcast_link_state sẽ không gửi nếu không có neighbors.
    #         # self.seq_num sẽ tăng, phản ánh LSP mới nhất (có thể là rỗng).
    #         self.broadcast_link_state()
    def __repr__(self):
        return (f"LSrouter(addr={self.addr}, "
                f"neighbors={list(self.neighbors.values())}, "
                f"seq_num={self.seq_num}, "
                f"FT_keys={list(self.forwarding_table.keys())})")