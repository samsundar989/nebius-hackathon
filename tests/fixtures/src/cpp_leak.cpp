#include <vector>
struct Node { std::vector<int> v; Node *next; };
int main() { Node *n = new Node{{1, 2, 3}, nullptr}; n->next = new Node{{4}, nullptr}; delete n; return 0; }
