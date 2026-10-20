
import pygame, numpy as np, sys
pygame.init(); pygame.display.set_mode((1,1))
def load(p):
    s = pygame.image.load(p); return pygame.surfarray.array3d(s).astype(np.int16)
A=load("artifacts/s11/smoke-fresh.png"); B=load("artifacts/s11/smoke-upgraded.png"); C=load("artifacts/s11/smoke-legacy.png")
def diff(x,y):
    d = np.abs(x-y).max(axis=2)
    return float((d>8).mean()*100)
print("fresh vs upgraded  %.3f%%" % diff(A,B))
print("fresh vs legacy    %.3f%%" % diff(A,C))
print("upgraded vs legacy %.3f%%" % diff(B,C))
