"""Additional explicit shared cameras: low engines and honest specimen tactical scale."""
import capture_slice as h
h.VIEWS={
 'tactical':h.VIEWS['tactical'],
 'escort-engine':dict(target=[-4200,-1,2550],distance=165.,yaw=178.,pitch=6.),
 'escort-tactical':dict(target=[-4200,0,2550],distance=650.,yaw=48.,pitch=55.),
 'yard-tactical':dict(target=[-4200,0,1600],distance=1600.,yaw=48.,pitch=55.),
}
h.main()
